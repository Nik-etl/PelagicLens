from __future__ import annotations

"""
PelagicLens
01_inventory_ices.py

Purpose
-------
Build a reproducible inventory of ICES Acoustic / Biotic hierarchical CSV files.

The script:
1. Scans:
      data/raw/ices/acoustic/
      data/raw/ices/biotic/
2. Parses ICES multi-section CSV files (Cruise, Haul, Catch, Biology, Data, EchoType, etc.).
3. Creates cruise/file inventories.
4. Extracts every species code found in Catch/Biology/EchoType records.
5. Resolves ICES species codes as WoRMS AphiaIDs using the WoRMS REST API.
6. Flags the PelagicLens target species:
      Engraulis encrasicolus
      AphiaID = 126426
7. Writes metadata tables to:
      data/metadata/

No third-party Python packages are required.

Recommended location
--------------------
PelagicLens/
└── models/
    └── scripts/
        └── 01_inventory_ices.py

Run from repository root:
    python .\models\scripts\01_inventory_ices.py

Offline run:
    python .\models\scripts\01_inventory_ices.py --no-resolve-species

Force a different repository root:
    python .\models\scripts\01_inventory_ices.py --repo-root "D:\.apps\PelagicLens"
"""

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# =============================================================================
# 1. PROJECT CONSTANTS
# =============================================================================

TARGET_APHIA_ID = "126426"
TARGET_SCIENTIFIC_NAME = "Engraulis encrasicolus"

WORMS_API = (
    "https://www.marinespecies.org/rest/"
    "AphiaRecordByAphiaID/{aphia_id}?marine_only=false"
)

WORMS_TAXON_URL = (
    "https://www.marinespecies.org/aphia.php?"
    "p=taxdetails&id={aphia_id}"
)


# =============================================================================
# 2. COMMAND-LINE ARGUMENTS
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory ICES acoustic/biotic hierarchical CSV files and "
            "resolve species AphiaIDs."
        )
    )

    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help=(
            "PelagicLens repository root. "
            "If omitted, it is inferred from this script location."
        ),
    )

    parser.add_argument(
        "--no-resolve-species",
        action="store_true",
        help=(
            "Do not query WoRMS. Species codes will still be extracted, "
            "but names will only come from an existing local cache."
        ),
    )

    parser.add_argument(
        "--refresh-species",
        action="store_true",
        help=(
            "Refresh taxonomic information from WoRMS even when a cached "
            "species name already exists."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Timeout in seconds for each WoRMS request. Default: 15.",
    )

    return parser.parse_args()


# =============================================================================
# 3. GENERIC HELPERS
# =============================================================================

def safe_float(value: object) -> Optional[float]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def derive_year(*values: object) -> Optional[int]:
    """
    Extract first plausible 4-digit year from dates, IDs, filenames, or paths.
    """
    for value in values:
        if value is None:
            continue

        match = re.search(r"(?:19|20)\d{2}", str(value))

        if match:
            return int(match.group())

    return None


def extract_aphia_ids(value: object) -> List[str]:
    """
    Extract numeric AphiaID-like values.

    ICES acoustic/biotic species fields use WoRMS AphiaID species references.
    Most species-level IDs are 5-7 digits, but the parser intentionally allows
    a broader numeric range for older/higher taxonomic records.
    """
    if value is None:
        return []

    text = str(value).strip()

    if not text:
        return []

    codes = re.findall(r"\b\d{3,9}\b", text)

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(codes))


def compact_join(values: Iterable[str]) -> str:
    clean = sorted({str(v).strip() for v in values if str(v).strip()})
    return ";".join(clean)


def json_compact(obj: object) -> str:
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


# =============================================================================
# 4. ICES HIERARCHICAL CSV PARSER
# =============================================================================

def iter_ices_records(path: Path) -> Iterator[Tuple[str, Dict[str, str]]]:
    """
    Read an ICES hierarchical CSV.

    ICES acoustic/biotic exports are not ordinary rectangular CSV tables.
    Different record blocks occur in the same file, e.g.:

        Cruise,Header,...
        Cruise,Record,...
        Haul,Header,...
        Haul,Record,...
        Catch,Header,...
        Catch,Record,...

    This generator returns:
        (section_name, record_dict)
    """

    headers: Dict[str, List[str]] = {}

    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:

        reader = csv.reader(handle)

        for line_number, row in enumerate(reader, start=1):

            if len(row) < 2:
                continue

            section = row[0].strip()
            row_type = row[1].strip()

            if not section:
                continue

            if row_type == "Header":
                headers[section] = [column.strip() for column in row[2:]]
                continue

            if row_type != "Record":
                continue

            header = headers.get(section)

            # Ignore malformed records that appeared before their header.
            if header is None:
                continue

            values = row[2:]

            if len(values) < len(header):
                values = values + [""] * (len(header) - len(values))

            record = dict(zip(header, values[: len(header)]))

            # Internal provenance fields.
            record["__section"] = section
            record["__line"] = str(line_number)
            record["__file"] = str(path)

            yield section, record


# =============================================================================
# 5. FILE DISCOVERY
# =============================================================================

def identify_file_type(path: Path) -> str:
    text = str(path).lower()
    name = path.name.lower()

    if "/acoustic/" in text.replace("\\", "/") or name.startswith("acoustic_"):
        return "acoustic"

    if "/biotic/" in text.replace("\\", "/") or name.startswith("biotic_"):
        return "biotic"

    return "unknown"


def scan_ices_files(
    acoustic_root: Path,
    biotic_root: Path,
) -> List[Path]:

    files: List[Path] = []

    for root in (acoustic_root, biotic_root):
        if root.exists():
            files.extend(root.rglob("*.csv"))

    return sorted(set(files))


# =============================================================================
# 6. SPATIAL BOUNDS
# =============================================================================

def empty_bounds() -> Dict[str, Optional[float]]:
    return {
        "lat_min": None,
        "lat_max": None,
        "lon_min": None,
        "lon_max": None,
    }


def update_bounds(
    bounds: Dict[str, Optional[float]],
    latitude: object,
    longitude: object,
) -> None:

    lat = safe_float(latitude)
    lon = safe_float(longitude)

    if lat is not None and -90 <= lat <= 90:
        bounds["lat_min"] = (
            lat if bounds["lat_min"] is None
            else min(bounds["lat_min"], lat)
        )
        bounds["lat_max"] = (
            lat if bounds["lat_max"] is None
            else max(bounds["lat_max"], lat)
        )

    if lon is not None and -180 <= lon <= 180:
        bounds["lon_min"] = (
            lon if bounds["lon_min"] is None
            else min(bounds["lon_min"], lon)
        )
        bounds["lon_max"] = (
            lon if bounds["lon_max"] is None
            else max(bounds["lon_max"], lon)
        )


def merge_bounds(
    target: Dict[str, Optional[float]],
    source: Dict[str, Optional[float]],
) -> None:

    for key in ("lat_min", "lon_min"):
        if source[key] is None:
            continue

        target[key] = (
            source[key]
            if target[key] is None
            else min(target[key], source[key])
        )

    for key in ("lat_max", "lon_max"):
        if source[key] is None:
            continue

        target[key] = (
            source[key]
            if target[key] is None
            else max(target[key], source[key])
        )


# =============================================================================
# 7. CRUISE STRUCTURE
# =============================================================================

def blank_cruise(cruise_key: str) -> dict:
    return {
        "cruise_key": cruise_key,
        "cruise_local_id": "",
        "year": None,
        "survey": "",
        "country": "",
        "platform": "",
        "organisation": "",
        "start_date": "",
        "end_date": "",
        "acoustic_files": set(),
        "biotic_files": set(),
        "section_counts": Counter(),
        "species_codes": set(),
        "stock_codes": set(),
        **empty_bounds(),
    }


# =============================================================================
# 8. TAXONOMY / SPECIES CODE LOOKUP
# =============================================================================

def lookup_worms(
    aphia_id: str,
    timeout: int = 15,
) -> Dict[str, str]:
    """
    Resolve one WoRMS AphiaID using the official WoRMS REST API.

    The script deliberately uses only Python standard-library networking,
    so requests / pandas are not required.
    """

    url = WORMS_API.format(aphia_id=aphia_id)

    request = Request(
        url,
        headers={
            "User-Agent": (
                "PelagicLens/0.1 "
                "(Copernicus Marine Service Hackathon; taxonomic lookup)"
            )
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        return {
            "aphia_id": aphia_id,
            "resolution_status": f"http_error_{exc.code}",
        }

    except (URLError, TimeoutError):
        return {
            "aphia_id": aphia_id,
            "resolution_status": "network_error",
        }

    except json.JSONDecodeError:
        return {
            "aphia_id": aphia_id,
            "resolution_status": "invalid_json",
        }

    if not isinstance(payload, dict):
        return {
            "aphia_id": aphia_id,
            "resolution_status": "unexpected_response",
        }

    return {
        "aphia_id": str(payload.get("AphiaID", aphia_id) or aphia_id),
        "scientific_name": payload.get("scientificname", "") or "",
        "valid_aphia_id": str(payload.get("valid_AphiaID", "") or ""),
        "valid_name": payload.get("valid_name", "") or "",
        "authority": payload.get("authority", "") or "",
        "status": payload.get("status", "") or "",
        "rank": payload.get("rank", "") or "",
        "kingdom": payload.get("kingdom", "") or "",
        "phylum": payload.get("phylum", "") or "",
        "class": payload.get("class", "") or "",
        "order": payload.get("order", "") or "",
        "family": payload.get("family", "") or "",
        "genus": payload.get("genus", "") or "",
        "resolution_status": "resolved",
    }


def load_species_cache(path: Path) -> Dict[str, Dict[str, str]]:
    cache: Dict[str, Dict[str, str]] = {}

    if not path.exists():
        return cache

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        for row in csv.DictReader(handle):
            code = (row.get("aphia_id") or "").strip()

            if code:
                cache[code] = row

    return cache


# =============================================================================
# 9. CSV OUTPUT WRITER
# =============================================================================

def write_csv(
    path: Path,
    rows: List[dict],
    fields: List[str],
) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(row)


# =============================================================================
# 10. MAIN INVENTORY
# =============================================================================

def main() -> None:
    args = parse_args()

    # -------------------------------------------------------------------------
    # Repository root
    # -------------------------------------------------------------------------

    if args.repo_root is not None:
        repo_root = args.repo_root.resolve()

    else:
        script_path = Path(__file__).resolve()

        # Expected:
        # repo/models/scripts/01_inventory_ices.py
        if script_path.parent.name == "scripts":
            repo_root = script_path.parents[2]
        else:
            repo_root = Path.cwd().resolve()

    acoustic_root = (
        repo_root
        / "data"
        / "raw"
        / "ices"
        / "acoustic"
    )

    biotic_root = (
        repo_root
        / "data"
        / "raw"
        / "ices"
        / "biotic"
    )

    metadata_root = (
        repo_root
        / "data"
        / "metadata"
    )

    metadata_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -------------------------------------------------------------------------
    # Find all source files
    # -------------------------------------------------------------------------

    source_files = scan_ices_files(
        acoustic_root,
        biotic_root,
    )

    if not source_files:
        raise SystemExit(
            "\nNo ICES CSV files were found.\n\n"
            f"Expected acoustic files under:\n  {acoustic_root}\n\n"
            f"Expected biotic files under:\n  {biotic_root}\n"
        )

    print("=" * 79)
    print("PELAGICLENS — ICES INVENTORY")
    print("=" * 79)
    print(f"Repository: {repo_root}")
    print(f"ICES CSV files found: {len(source_files)}")
    print()

    # -------------------------------------------------------------------------
    # Main accumulators
    # -------------------------------------------------------------------------

    file_inventory: List[dict] = []

    cruises: Dict[str, dict] = {}

    # Global species statistics:
    # species_stats[aphia_id]["catch_records"], etc.
    species_stats: Dict[str, Counter] = defaultdict(Counter)

    # Species by cruise.
    #
    # Key:
    # (CruiseLocalID, AphiaID, CatchSpeciesCategory)
    #
    # Value:
    # counters, catch weights, stock codes.
    species_by_cruise: Dict[Tuple[str, str, str], dict] = {}

    acoustic_echo_species: List[dict] = []

    # -------------------------------------------------------------------------
    # Parse each raw file
    # -------------------------------------------------------------------------

    for file_number, path in enumerate(source_files, start=1):

        print(
            f"[{file_number:>3}/{len(source_files)}] "
            f"{path.relative_to(repo_root)}"
        )

        file_type = identify_file_type(path)

        section_counts: Counter = Counter()

        cruise_meta: Dict[str, str] = {}

        bounds = empty_bounds()

        file_species_codes = set()

        file_stock_codes = set()

        # EchoType appears before Cruise in some ICES acoustic files,
        # therefore it is temporarily stored until CruiseLocalID is known.
        pending_echo_records: List[dict] = []

        # ---------------------------------------------------------------------
        # Single-pass streaming parser.
        # Important: do NOT load million-row files into memory.
        # ---------------------------------------------------------------------

        for section, record in iter_ices_records(path):

            section_counts[section] += 1

            # -----------------------------------------------------------------
            # Cruise
            # -----------------------------------------------------------------

            if section == "Cruise":
                cruise_meta = record.copy()
                continue

            # -----------------------------------------------------------------
            # Acoustic observations
            # -----------------------------------------------------------------

            if section == "Data":

                update_bounds(
                    bounds,
                    record.get("LogLatitude"),
                    record.get("LogLongitude"),
                )

                continue

            # -----------------------------------------------------------------
            # Hauls
            # -----------------------------------------------------------------

            if section == "Haul":

                update_bounds(
                    bounds,
                    record.get("HaulStartLatitude"),
                    record.get("HaulStartLongitude"),
                )

                update_bounds(
                    bounds,
                    record.get("HaulStopLatitude"),
                    record.get("HaulStopLongitude"),
                )

                continue

            # -----------------------------------------------------------------
            # Catch + individual biology
            # -----------------------------------------------------------------

            if section in ("Catch", "Biology"):

                codes = extract_aphia_ids(
                    record.get("CatchSpeciesCode")
                )

                cruise_id_from_record = (
                    record.get("CruiseLocalID")
                    or cruise_meta.get("CruiseLocalID")
                    or ""
                ).strip()

                category = (
                    record.get("CatchSpeciesCategory")
                    or ""
                ).strip()

                for aphia_id in codes:

                    file_species_codes.add(aphia_id)

                    species_stats[aphia_id][
                        f"{section.lower()}_records"
                    ] += 1

                    key = (
                        cruise_id_from_record,
                        aphia_id,
                        category,
                    )

                    if key not in species_by_cruise:
                        species_by_cruise[key] = {
                            "catch_records": 0,
                            "biology_records": 0,
                            "catch_number_sum": 0.0,
                            "catch_weights": defaultdict(float),
                            "biology_stock_codes": set(),
                        }

                    aggregation = species_by_cruise[key]

                    if section == "Catch":

                        aggregation["catch_records"] += 1

                        catch_number = safe_float(
                            record.get(
                                "CatchSpeciesCategoryNumber"
                            )
                        )

                        if catch_number is not None:
                            aggregation[
                                "catch_number_sum"
                            ] += catch_number

                        catch_weight = safe_float(
                            record.get(
                                "CatchSpeciesCategoryWeight"
                            )
                        )

                        weight_unit = (
                            record.get("CatchWeightUnit")
                            or ""
                        ).strip()

                        if catch_weight is not None:

                            unit_key = (
                                weight_unit
                                if weight_unit
                                else "unspecified"
                            )

                            aggregation[
                                "catch_weights"
                            ][unit_key] += catch_weight

                    else:
                        aggregation["biology_records"] += 1

                        stock_code = (
                            record.get("BiologyStockCode")
                            or ""
                        ).strip()

                        if stock_code:
                            aggregation[
                                "biology_stock_codes"
                            ].add(stock_code)

                            file_stock_codes.add(stock_code)

                continue

            # -----------------------------------------------------------------
            # Acoustic EchoType species allocation
            # -----------------------------------------------------------------

            if section == "EchoType":

                codes = extract_aphia_ids(
                    record.get("EchoTypeSpeciesCode")
                )

                for aphia_id in codes:

                    file_species_codes.add(aphia_id)

                    species_stats[aphia_id][
                        "echo_type_records"
                    ] += 1

                    pending_echo_records.append(
                        {
                            "aphia_id": aphia_id,
                            "echo_type_id": (
                                record.get("EchoTypeID")
                                or ""
                            ),
                            "echo_type_stratum": (
                                record.get(
                                    "EchoTypeStratum"
                                )
                                or ""
                            ),
                            "echo_species_category": (
                                record.get(
                                    "EchoTypeSpeciesCategory"
                                )
                                or ""
                            ),
                            "echo_comments": (
                                record.get(
                                    "EchoTypeComments"
                                )
                                or ""
                            ),
                        }
                    )

                continue

        # ---------------------------------------------------------------------
        # File-level cruise metadata
        # ---------------------------------------------------------------------

        cruise_local_id = (
            cruise_meta.get("CruiseLocalID")
            or path.stem
        ).strip()

        survey = (
            cruise_meta.get("CruiseSurvey")
            or ""
        ).strip()

        country = (
            cruise_meta.get("CruiseCountry")
            or ""
        ).strip()

        platform = (
            cruise_meta.get("CruisePlatform")
            or ""
        ).strip()

        organisation = (
            cruise_meta.get("CruiseOrganisation")
            or ""
        ).strip()

        start_date = (
            cruise_meta.get("CruiseStartDate")
            or ""
        ).strip()

        end_date = (
            cruise_meta.get("CruiseEndDate")
            or ""
        ).strip()

        year = derive_year(
            start_date,
            cruise_local_id,
            path,
        )

        # ---------------------------------------------------------------------
        # Add pending acoustic EchoType records
        # ---------------------------------------------------------------------

        for row in pending_echo_records:

            acoustic_echo_species.append(
                {
                    "source_file": str(
                        path.relative_to(repo_root)
                    ),
                    "year": year or "",
                    "survey": survey,
                    "country": country,
                    "platform": platform,
                    "cruise_local_id": cruise_local_id,
                    **row,
                }
            )

        # ---------------------------------------------------------------------
        # Cruise aggregation
        # ---------------------------------------------------------------------

        cruise_key = cruise_local_id

        cruise = cruises.setdefault(
            cruise_key,
            blank_cruise(cruise_key),
        )

        if not cruise["cruise_local_id"]:
            cruise["cruise_local_id"] = cruise_local_id

        if cruise["year"] is None:
            cruise["year"] = year

        if not cruise["survey"]:
            cruise["survey"] = survey

        if not cruise["country"]:
            cruise["country"] = country

        if not cruise["platform"]:
            cruise["platform"] = platform

        if not cruise["organisation"]:
            cruise["organisation"] = organisation

        if not cruise["start_date"]:
            cruise["start_date"] = start_date

        if not cruise["end_date"]:
            cruise["end_date"] = end_date

        cruise["section_counts"].update(
            section_counts
        )

        if file_type == "acoustic":
            cruise["acoustic_files"].add(
                str(path.relative_to(repo_root))
            )

        elif file_type == "biotic":
            cruise["biotic_files"].add(
                str(path.relative_to(repo_root))
            )

        cruise["species_codes"].update(
            file_species_codes
        )

        cruise["stock_codes"].update(
            file_stock_codes
        )

        merge_bounds(
            cruise,
            bounds,
        )

        # ---------------------------------------------------------------------
        # File inventory row
        # ---------------------------------------------------------------------

        file_inventory.append(
            {
                "file_type": file_type,
                "source_file": str(
                    path.relative_to(repo_root)
                ),
                "year": year or "",
                "survey": survey,
                "country": country,
                "platform": platform,
                "organisation": organisation,
                "cruise_local_id": cruise_local_id,
                "start_date": start_date,
                "end_date": end_date,

                "n_instrument": section_counts.get(
                    "Instrument", 0
                ),
                "n_calibration": section_counts.get(
                    "Calibration", 0
                ),
                "n_data_acquisition": section_counts.get(
                    "DataAcquisition", 0
                ),
                "n_data_processing": section_counts.get(
                    "DataProcessing", 0
                ),
                "n_echo_type": section_counts.get(
                    "EchoType", 0
                ),
                "n_acoustic_data": section_counts.get(
                    "Data", 0
                ),
                "n_haul": section_counts.get(
                    "Haul", 0
                ),
                "n_catch": section_counts.get(
                    "Catch", 0
                ),
                "n_biology": section_counts.get(
                    "Biology", 0
                ),

                "n_species_codes": len(
                    file_species_codes
                ),
                "species_codes": compact_join(
                    file_species_codes
                ),
                "stock_codes": compact_join(
                    file_stock_codes
                ),

                "lat_min": bounds["lat_min"],
                "lat_max": bounds["lat_max"],
                "lon_min": bounds["lon_min"],
                "lon_max": bounds["lon_max"],
            }
        )

    # =========================================================================
    # 11. BUILD CRUISE INVENTORY
    # =========================================================================

    cruise_inventory: List[dict] = []

    for cruise in cruises.values():

        counts = cruise["section_counts"]

        species_codes = cruise["species_codes"]

        cruise_inventory.append(
            {
                "year": cruise["year"] or "",
                "survey": cruise["survey"],
                "country": cruise["country"],
                "platform": cruise["platform"],
                "organisation": cruise["organisation"],
                "cruise_local_id": cruise[
                    "cruise_local_id"
                ],
                "start_date": cruise["start_date"],
                "end_date": cruise["end_date"],

                "acoustic_file_n": len(
                    cruise["acoustic_files"]
                ),
                "biotic_file_n": len(
                    cruise["biotic_files"]
                ),

                "acoustic_n": counts.get(
                    "Data", 0
                ),
                "haul_n": counts.get(
                    "Haul", 0
                ),
                "catch_n": counts.get(
                    "Catch", 0
                ),
                "biology_n": counts.get(
                    "Biology", 0
                ),
                "echo_type_n": counts.get(
                    "EchoType", 0
                ),

                "species_code_n": len(
                    species_codes
                ),

                "target_anchovy_present": (
                    TARGET_APHIA_ID
                    in species_codes
                ),

                "species_codes": compact_join(
                    species_codes
                ),

                "stock_codes": compact_join(
                    cruise["stock_codes"]
                ),

                "lat_min": cruise["lat_min"],
                "lat_max": cruise["lat_max"],
                "lon_min": cruise["lon_min"],
                "lon_max": cruise["lon_max"],
            }
        )

    cruise_inventory.sort(
        key=lambda row: (
            str(row["year"]),
            row["survey"],
            row["cruise_local_id"],
        )
    )

    # =========================================================================
    # 12. RESOLVE SPECIES CODES
    # =========================================================================

    species_cache_path = (
        metadata_root
        / "worms_species_cache.csv"
    )

    species_cache = load_species_cache(
        species_cache_path
    )

    # Always add anchovy, even if it is not found in the current raw files.
    all_aphia_ids = (
        set(species_stats.keys())
        | {TARGET_APHIA_ID}
    )

    if not args.no_resolve_species:

        codes_to_resolve = []

        for aphia_id in all_aphia_ids:

            cached_name = (
                species_cache
                .get(aphia_id, {})
                .get("scientific_name", "")
            )

            if (
                args.refresh_species
                or not cached_name
            ):
                codes_to_resolve.append(
                    aphia_id
                )

        codes_to_resolve.sort(
            key=int
        )

        if codes_to_resolve:
            print()
            print(
                "Resolving species codes "
                "with WoRMS..."
            )

        for index, aphia_id in enumerate(
            codes_to_resolve,
            start=1,
        ):

            print(
                f"  {index:>3}/"
                f"{len(codes_to_resolve)} "
                f"AphiaID {aphia_id}"
            )

            resolved = lookup_worms(
                aphia_id,
                timeout=args.timeout,
            )

            old = species_cache.get(
                aphia_id,
                {},
            )

            species_cache[aphia_id] = {
                **old,
                **resolved,
            }

            # Gentle delay between calls.
            time.sleep(0.05)

    # =========================================================================
    # 13. SPECIES REFERENCE TABLE
    # =========================================================================

    species_reference: List[dict] = []

    for aphia_id in sorted(
        all_aphia_ids,
        key=int,
    ):

        taxonomy = species_cache.get(
            aphia_id,
            {},
        )

        scientific_name = (
            taxonomy.get(
                "scientific_name",
                "",
            )
        )

        # Known target fallback.
        if (
            aphia_id == TARGET_APHIA_ID
            and not scientific_name
        ):
            scientific_name = (
                TARGET_SCIENTIFIC_NAME
            )

        species_reference.append(
            {
                "aphia_id": aphia_id,

                "scientific_name": scientific_name,

                "valid_aphia_id": taxonomy.get(
                    "valid_aphia_id",
                    "",
                ),

                "valid_name": taxonomy.get(
                    "valid_name",
                    "",
                ),

                "authority": taxonomy.get(
                    "authority",
                    "",
                ),

                "status": taxonomy.get(
                    "status",
                    "",
                ),

                "rank": taxonomy.get(
                    "rank",
                    "",
                ),

                "family": taxonomy.get(
                    "family",
                    "",
                ),

                "genus": taxonomy.get(
                    "genus",
                    "",
                ),

                "catch_records": (
                    species_stats[
                        aphia_id
                    ].get(
                        "catch_records",
                        0,
                    )
                ),

                "biology_records": (
                    species_stats[
                        aphia_id
                    ].get(
                        "biology_records",
                        0,
                    )
                ),

                "echo_type_records": (
                    species_stats[
                        aphia_id
                    ].get(
                        "echo_type_records",
                        0,
                    )
                ),

                "found_in_raw": (
                    aphia_id
                    in species_stats
                ),

                "is_target_species": (
                    aphia_id
                    == TARGET_APHIA_ID
                ),

                "resolution_status": (
                    taxonomy.get(
                        "resolution_status",
                        "not_resolved",
                    )
                ),

                "worms_url": (
                    WORMS_TAXON_URL.format(
                        aphia_id=aphia_id
                    )
                ),
            }
        )

    species_name_index = {
        row["aphia_id"]:
        row["scientific_name"]
        for row in species_reference
    }

    # =========================================================================
    # 14. SPECIES BY CRUISE
    # =========================================================================

    cruise_index = {
        row["cruise_local_id"]: row
        for row in cruise_inventory
    }

    species_by_cruise_rows: List[dict] = []

    for (
        cruise_local_id,
        aphia_id,
        species_category,
    ), aggregation in sorted(
        species_by_cruise.items(),
        key=lambda item: (
            item[0][0],
            int(item[0][1]),
            item[0][2],
        ),
    ):

        cruise = cruise_index.get(
            cruise_local_id,
            {},
        )

        catch_weights = dict(
            sorted(
                aggregation[
                    "catch_weights"
                ].items()
            )
        )

        species_by_cruise_rows.append(
            {
                "year": cruise.get(
                    "year", ""
                ),

                "survey": cruise.get(
                    "survey", ""
                ),

                "country": cruise.get(
                    "country", ""
                ),

                "platform": cruise.get(
                    "platform", ""
                ),

                "cruise_local_id": (
                    cruise_local_id
                ),

                "aphia_id": aphia_id,

                "scientific_name": (
                    species_name_index.get(
                        aphia_id,
                        "",
                    )
                ),

                "species_category": (
                    species_category
                ),

                "catch_records": (
                    aggregation[
                        "catch_records"
                    ]
                ),

                "biology_records": (
                    aggregation[
                        "biology_records"
                    ]
                ),

                "catch_number_sum": (
                    aggregation[
                        "catch_number_sum"
                    ]
                ),

                # JSON preserves units safely:
                # {"kg":123.4}
                # instead of incorrectly adding kg + g.
                "catch_weight_by_unit": (
                    json_compact(
                        catch_weights
                    )
                    if catch_weights
                    else ""
                ),

                "biology_stock_codes": (
                    compact_join(
                        aggregation[
                            "biology_stock_codes"
                        ]
                    )
                ),

                "is_target_species": (
                    aphia_id
                    == TARGET_APHIA_ID
                ),
            }
        )

    # =========================================================================
    # 15. ADD SPECIES NAMES TO ECHOTYPE TABLE
    # =========================================================================

    for row in acoustic_echo_species:
        row["scientific_name"] = (
            species_name_index.get(
                row["aphia_id"],
                "",
            )
        )

        row["is_target_species"] = (
            row["aphia_id"]
            == TARGET_APHIA_ID
        )

    # =========================================================================
    # 16. WRITE TAXONOMIC CACHE
    # =========================================================================

    cache_fields = [
        "aphia_id",
        "scientific_name",
        "valid_aphia_id",
        "valid_name",
        "authority",
        "status",
        "rank",
        "kingdom",
        "phylum",
        "class",
        "order",
        "family",
        "genus",
        "resolution_status",
    ]

    cache_rows: List[dict] = []

    for aphia_id in sorted(
        species_cache.keys(),
        key=lambda value: (
            int(value)
            if str(value).isdigit()
            else value
        ),
    ):

        row = dict(
            species_cache[aphia_id]
        )

        row["aphia_id"] = aphia_id

        cache_rows.append(row)

    write_csv(
        species_cache_path,
        cache_rows,
        cache_fields,
    )

    # =========================================================================
    # 17. WRITE OUTPUT TABLES
    # =========================================================================

    if file_inventory:
        write_csv(
            metadata_root
            / "ices_file_inventory.csv",
            file_inventory,
            list(file_inventory[0].keys()),
        )

    if cruise_inventory:
        write_csv(
            metadata_root
            / "ices_survey_inventory.csv",
            cruise_inventory,
            list(
                cruise_inventory[0].keys()
            ),
        )

    if species_reference:
        write_csv(
            metadata_root
            / "ices_species_reference.csv",
            species_reference,
            list(
                species_reference[0].keys()
            ),
        )

    if species_by_cruise_rows:
        write_csv(
            metadata_root
            / "ices_species_by_cruise.csv",
            species_by_cruise_rows,
            list(
                species_by_cruise_rows[0]
                .keys()
            ),
        )

    if acoustic_echo_species:
        write_csv(
            metadata_root
            / "ices_echo_species.csv",
            acoustic_echo_species,
            list(
                acoustic_echo_species[0]
                .keys()
            ),
        )

    # =========================================================================
    # 18. TERMINAL SUMMARY
    # =========================================================================

    anchovy_cruises = [
        row
        for row in cruise_inventory
        if row["target_anchovy_present"]
    ]

    print()
    print("=" * 79)
    print("ICES INVENTORY COMPLETE")
    print("=" * 79)

    print(
        f"Raw CSV files: "
        f"{len(source_files)}"
    )

    print(
        f"Cruises: "
        f"{len(cruise_inventory)}"
    )

    print(
        f"Species AphiaIDs found: "
        f"{len(species_stats)}"
    )

    print()

    print(
        "PelagicLens target species:"
    )

    print(
        f"  {TARGET_SCIENTIFIC_NAME}"
    )

    print(
        f"  AphiaID: "
        f"{TARGET_APHIA_ID}"
    )

    print(
        f"  Cruises containing target: "
        f"{len(anchovy_cruises)}"
    )

    if anchovy_cruises:

        print()

        for row in anchovy_cruises:

            print(
                "  - "
                f"{row['year']} | "
                f"{row['survey']} | "
                f"{row['country']} | "
                f"{row['cruise_local_id']}"
            )

    print()
    print(
        f"Metadata output directory:\n"
        f"  {metadata_root}"
    )

    print()

    output_names = [
        "ices_file_inventory.csv",
        "ices_survey_inventory.csv",
        "ices_species_reference.csv",
        "ices_species_by_cruise.csv",
        "worms_species_cache.csv",
    ]

    if (
        metadata_root
        / "ices_echo_species.csv"
    ).exists():

        output_names.append(
            "ices_echo_species.csv"
        )

    for name in output_names:

        output_path = (
            metadata_root
            / name
        )

        if output_path.exists():
            print(
                f"  [OK] {name}"
            )

    print()
    print(
        "IMPORTANT: CatchSpeciesCode / "
        "EchoTypeSpeciesCode are treated "
        "as WoRMS AphiaIDs."
    )

    print(
        "Example target:"
    )

    print(
        "  Engraulis encrasicolus "
        "= AphiaID 126426"
    )

    print()

    if args.no_resolve_species:
        print(
            "Species-name resolution was disabled."
        )
        print(
            "Run again without "
            "--no-resolve-species "
            "to query WoRMS."
        )

    print("=" * 79)


# =============================================================================
# 19. ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()
