# ==============================================================================
# PelagicLens
# 02_download_pelgas.R
#
# Download reproducible public PELGAS datasets from SEANOE (Ifremer/SISMER).
#
# WHY THIS ROUTE?
# - ICES Acoustic provides public CSV/XML downloads through its portal, but a
#   stable, publicly documented download API for the portal is not exposed in
#   the current public interface.
# - SEANOE exposes a REST metadata endpoint and hosts several published PELGAS
#   datasets with persistent DOIs. This is the safest programmatic route for
#   the PelagicLens MVP.
#
# CORE DATASETS
# 10.17882/53389 : Gridded maps of PELGAS ecosystem parameters (spatial; core)
# 10.17882/59809 : Biotic identification-trawl data, PELGAS 2000-2018 (core)
# 10.17882/53388 : Biomass and abundance at length of small pelagic fish
#
# IMPORTANT
# Do NOT install.packages("echor") expecting the Ifremer fisheries-acoustics
# package. The CRAN package named "echor" is an unrelated US EPA package.
#
# Run from repository root:
#   PS D:\.apps\PelagicLens> Rscript .\models\scripts\02_download_pelgas.R
#
# Dry run (discover URLs, do not download):
#   Rscript .\models\scripts\02_download_pelgas.R --dry-run
#
# Select datasets:
#   Rscript .\models\scripts\02_download_pelgas.R --ids=53389,59809
# ==============================================================================

options(
  timeout = max(600, getOption("timeout")),
  stringsAsFactors = FALSE
)

# ------------------------------------------------------------------------------
# 0. Command line
# ------------------------------------------------------------------------------

args <- commandArgs(trailingOnly = TRUE)

DRY_RUN <- "--dry-run" %in% args

ids_arg <- grep("^--ids=", args, value = TRUE)

if (length(ids_arg) > 0) {
  REQUESTED_IDS <- strsplit(sub("^--ids=", "", ids_arg[1]), ",", fixed = TRUE)[[1]]
  REQUESTED_IDS <- trimws(REQUESTED_IDS)
} else {
  REQUESTED_IDS <- c("53389", "59809", "53388")
}

# ------------------------------------------------------------------------------
# 1. Packages
# ------------------------------------------------------------------------------

required_packages <- c(
  "httr2",
  "jsonlite",
  "rvest",
  "xml2",
  "dplyr",
  "purrr",
  "stringr",
  "tibble",
  "readr",
  "fs",
  "curl"
)

missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)
]

if (length(missing_packages) > 0) {
  message(
    "Installing missing packages: ",
    paste(missing_packages, collapse = ", ")
  )
  install.packages(missing_packages, repos = "https://cloud.r-project.org")
}

suppressPackageStartupMessages({
  library(httr2)
  library(jsonlite)
  library(rvest)
  library(xml2)
  library(dplyr)
  library(purrr)
  library(stringr)
  library(tibble)
  library(readr)
  library(fs)
  library(curl)
})

# ------------------------------------------------------------------------------
# 2. Project root
# ------------------------------------------------------------------------------

find_repo_root <- function(start = getwd()) {
  p <- fs::path_abs(start)

  repeat {
    if (
      fs::dir_exists(fs::path(p, "models")) ||
      fs::file_exists(fs::path(p, "README.md"))
    ) {
      return(p)
    }

    parent <- fs::path_dir(p)

    if (identical(parent, p)) {
      stop(
        "Could not infer the PelagicLens repository root.\n",
        "Run this script from D:/\\.apps/PelagicLens or a subfolder."
      )
    }

    p <- parent
  }
}

REPO_ROOT <- find_repo_root()

RAW_ROOT <- fs::path(
  REPO_ROOT,
  "data",
  "raw",
  "pelgas",
  "seanoe"
)

META_ROOT <- fs::path(
  REPO_ROOT,
  "data",
  "metadata"
)

fs::dir_create(RAW_ROOT, recurse = TRUE)
fs::dir_create(META_ROOT, recurse = TRUE)

message("Repository: ", REPO_ROOT)
message("Raw PELGAS directory: ", RAW_ROOT)
message("Metadata directory: ", META_ROOT)
message("Dry run: ", DRY_RUN)
message("")

# ------------------------------------------------------------------------------
# 3. Dataset registry
# ------------------------------------------------------------------------------

datasets <- tibble::tribble(
  ~id,     ~doi,                 ~label,                         ~role,       ~known_period,
  "53389", "10.17882/53389",     "gridded_ecosystem_parameters", "CORE",      "2000-2016",
  "59809", "10.17882/59809",     "biotic_identification_trawls", "CORE",      "2000-2018",
  "53388", "10.17882/53388",     "biomass_abundance_at_length",  "SUPPORT",   "check metadata"
) |>
  dplyr::filter(id %in% REQUESTED_IDS)

if (nrow(datasets) == 0) {
  stop(
    "None of the requested IDs are in the local PELGAS registry: ",
    paste(REQUESTED_IDS, collapse = ", ")
  )
}

# ------------------------------------------------------------------------------
# 4. HTTP helpers
# ------------------------------------------------------------------------------

user_agent_string <- paste(
  "PelagicLens/0.1",
  "(Copernicus Marine Service Hackathon;",
  "public scientific data download)"
)

safe_perform <- function(req) {
  tryCatch(
    httr2::req_perform(req),
    error = function(e) {
      message("HTTP error: ", conditionMessage(e))
      NULL
    }
  )
}

resolve_doi <- function(doi) {
  url <- paste0("https://doi.org/", doi)

  req <- httr2::request(url) |>
    httr2::req_user_agent(user_agent_string) |>
    httr2::req_options(followlocation = TRUE)

  resp <- safe_perform(req)

  if (is.null(resp)) {
    return(NA_character_)
  }

  httr2::resp_url(resp)
}

get_seanoe_metadata <- function(id) {
  url <- paste0(
    "https://www.seanoe.org/api/find-by-id/",
    id
  )

  req <- httr2::request(url) |>
    httr2::req_user_agent(user_agent_string) |>
    httr2::req_headers(
      Accept = "application/json"
    )

  resp <- safe_perform(req)

  if (is.null(resp)) {
    return(NULL)
  }

  if (httr2::resp_status(resp) >= 400) {
    message(
      "SEANOE API returned HTTP ",
      httr2::resp_status(resp),
      " for dataset ",
      id
    )
    return(NULL)
  }

  txt <- httr2::resp_body_string(resp)

  out <- tryCatch(
    jsonlite::fromJSON(
      txt,
      simplifyVector = FALSE
    ),
    error = function(e) NULL
  )

  if (is.null(out)) {
    message(
      "Could not parse SEANOE JSON for dataset ",
      id
    )
  }

  out
}

# ------------------------------------------------------------------------------
# 5. Recursively collect URLs from an arbitrary JSON structure
# ------------------------------------------------------------------------------

collect_urls <- function(x, path = "root") {
  rows <- list()

  walk <- function(obj, current_path) {

    if (is.null(obj)) {
      return(invisible(NULL))
    }

    if (is.character(obj)) {
      for (i in seq_along(obj)) {
        value <- obj[[i]]

        if (
          !is.na(value) &&
          stringr::str_detect(
            value,
            regex("^https?://", ignore_case = TRUE)
          )
        ) {
          rows[[length(rows) + 1]] <<- tibble::tibble(
            context = current_path,
            url = value
          )
        }
      }

      return(invisible(NULL))
    }

    if (is.list(obj)) {
      nms <- names(obj)

      for (i in seq_along(obj)) {
        child_name <- if (
          !is.null(nms) &&
          length(nms) >= i &&
          nzchar(nms[[i]])
        ) {
          nms[[i]]
        } else {
          as.character(i)
        }

        walk(
          obj[[i]],
          paste0(
            current_path,
            "/",
            child_name
          )
        )
      }
    }

    invisible(NULL)
  }

  walk(x, path)

  if (length(rows) == 0) {
    return(
      tibble::tibble(
        context = character(),
        url = character()
      )
    )
  }

  dplyr::bind_rows(rows) |>
    dplyr::distinct()
}

# ------------------------------------------------------------------------------
# 6. Scrape SEANOE landing page as a fallback / complement to the REST API
# ------------------------------------------------------------------------------

scrape_landing_links <- function(landing_url) {

  if (is.na(landing_url) || !nzchar(landing_url)) {
    return(
      tibble::tibble(
        context = character(),
        url = character()
      )
    )
  }

  page <- tryCatch(
    rvest::read_html(landing_url),
    error = function(e) NULL
  )

  if (is.null(page)) {
    message(
      "Could not read landing page: ",
      landing_url
    )

    return(
      tibble::tibble(
        context = character(),
        url = character()
      )
    )
  }

  anchors <- rvest::html_elements(page, "a")

  if (length(anchors) == 0) {
    return(
      tibble::tibble(
        context = character(),
        url = character()
      )
    )
  }

  href <- rvest::html_attr(anchors, "href")
  txt  <- rvest::html_text2(anchors)

  keep <- !is.na(href) & nzchar(href)

  href <- href[keep]
  txt  <- txt[keep]

  absolute <- xml2::url_absolute(
    href,
    landing_url
  )

  tibble::tibble(
    context = paste0(
      "landing/a:",
      txt
    ),
    url = absolute
  ) |>
    dplyr::distinct()
}

# ------------------------------------------------------------------------------
# 7. Candidate scoring
# ------------------------------------------------------------------------------

score_candidate <- function(context, url) {

  score <- 0L

  x <- paste(context, url)

  if (
    stringr::str_detect(
      x,
      regex(
        "download|raw.?data|processed.?data|file|fichier|resource|distribution",
        ignore_case = TRUE
      )
    )
  ) {
    score <- score + 3L
  }

  if (
    stringr::str_detect(
      url,
      regex(
        "\\.(csv|tsv|txt|zip|gz|tar|7z|xlsx|xls|ods|rds|rdata|nc|netcdf|json|xml)(\\?|$)",
        ignore_case = TRUE
      )
    )
  ) {
    score <- score + 3L
  }

  if (
    stringr::str_detect(
      url,
      regex(
        "/download|download=|attachment|file=",
        ignore_case = TRUE
      )
    )
  ) {
    score <- score + 4L
  }

  if (
    stringr::str_detect(
      url,
      fixed("seanoe.org", ignore_case = TRUE)
    )
  ) {
    score <- score + 1L
  }

  # Explicit penalties for metadata/navigation links.
  if (
    stringr::str_detect(
      url,
      regex(
        "doi\\.org|OAIHandler|/api/find-by-id/|mailto:|javascript:",
        ignore_case = TRUE
      )
    )
  ) {
    score <- score - 10L
  }

  # A canonical landing page by itself is not a raw data file.
  if (
    stringr::str_detect(
      url,
      regex(
        "seanoe\\.org/data/[0-9]+/[0-9]+/?$",
        ignore_case = TRUE
      )
    )
  ) {
    score <- score - 8L
  }

  score
}

build_candidate_table <- function(metadata, landing_url) {

  from_api <- if (!is.null(metadata)) {
    collect_urls(metadata, "api")
  } else {
    tibble::tibble(
      context = character(),
      url = character()
    )
  }

  from_html <- scrape_landing_links(
    landing_url
  )

  out <- dplyr::bind_rows(
    from_api,
    from_html
  ) |>
    dplyr::distinct(url, .keep_all = TRUE)

  if (nrow(out) == 0) {
    return(
      tibble::tibble(
        context = character(),
        url = character(),
        score = integer()
      )
    )
  }

  out |>
    dplyr::mutate(
      score = purrr::map2_int(
        context,
        url,
        score_candidate
      )
    ) |>
    dplyr::arrange(
      dplyr::desc(score),
      url
    )
}

# ------------------------------------------------------------------------------
# 8. Probe headers to distinguish files from HTML pages
# ------------------------------------------------------------------------------

probe_url <- function(url) {

  req <- httr2::request(url) |>
    httr2::req_method("HEAD") |>
    httr2::req_user_agent(user_agent_string) |>
    httr2::req_options(followlocation = TRUE)

  resp <- safe_perform(req)

  if (is.null(resp)) {
    return(
      tibble::tibble(
        probe_ok = FALSE,
        status = NA_integer_,
        final_url = url,
        content_type = NA_character_,
        content_disposition = NA_character_,
        content_length = NA_character_
      )
    )
  }

  tibble::tibble(
    probe_ok = TRUE,
    status = httr2::resp_status(resp),
    final_url = httr2::resp_url(resp),
    content_type = httr2::resp_header(
      resp,
      "content-type"
    ) %||% NA_character_,
    content_disposition = httr2::resp_header(
      resp,
      "content-disposition"
    ) %||% NA_character_,
    content_length = httr2::resp_header(
      resp,
      "content-length"
    ) %||% NA_character_
  )
}

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || is.na(x) || !nzchar(x)) {
    y
  } else {
    x
  }
}

# ------------------------------------------------------------------------------
# 9. File-name helpers
# ------------------------------------------------------------------------------

sanitize_filename <- function(x) {
  x |>
    utils::URLdecode() |>
    stringr::str_replace_all(
      "[\\\\/:*?\"<>|]",
      "_"
    ) |>
    stringr::str_replace_all(
      "\\s+",
      "_"
    ) |>
    stringr::str_sub(1, 180)
}

filename_from_disposition <- function(x) {

  if (
    is.na(x) ||
    !nzchar(x)
  ) {
    return(NA_character_)
  }

  # filename*=UTF-8''name.csv
  m1 <- stringr::str_match(
    x,
    regex(
      "filename\\*\\s*=\\s*UTF-8''([^;]+)",
      ignore_case = TRUE
    )
  )

  if (!is.na(m1[1, 2])) {
    return(
      sanitize_filename(
        gsub(
          '^"|"$',
          "",
          m1[1, 2]
        )
      )
    )
  }

  # filename="name.csv"
  m2 <- stringr::str_match(
    x,
    regex(
      'filename\\s*=\\s*"?([^";]+)"?',
      ignore_case = TRUE
    )
  )

  if (!is.na(m2[1, 2])) {
    return(
      sanitize_filename(
        m2[1, 2]
      )
    )
  }

  NA_character_
}

extension_from_content_type <- function(content_type) {

  if (is.na(content_type)) {
    return("")
  }

  ct <- tolower(content_type)

  if (grepl("zip", ct)) return(".zip")
  if (grepl("gzip", ct)) return(".gz")
  if (grepl("csv", ct)) return(".csv")
  if (grepl("spreadsheet|excel", ct)) return(".xlsx")
  if (grepl("netcdf", ct)) return(".nc")
  if (grepl("json", ct)) return(".json")
  if (grepl("xml", ct)) return(".xml")
  if (grepl("tab-separated", ct)) return(".tsv")
  if (grepl("text/plain", ct)) return(".txt")

  ""
}

make_filename <- function(
  dataset_id,
  index,
  url,
  content_type = NA_character_,
  content_disposition = NA_character_
) {

  from_header <- filename_from_disposition(
    content_disposition
  )

  if (
    !is.na(from_header) &&
    nzchar(from_header)
  ) {
    return(from_header)
  }

  path_part <- sub(
    "\\?.*$",
    "",
    url
  )

  from_url <- basename(path_part)
  from_url <- sanitize_filename(from_url)

  if (
    nzchar(from_url) &&
    grepl("\\.[A-Za-z0-9]{1,8}$", from_url)
  ) {
    return(from_url)
  }

  ext <- extension_from_content_type(
    content_type
  )

  sprintf(
    "seanoe_%s_%02d%s",
    dataset_id,
    index,
    ext
  )
}

# ------------------------------------------------------------------------------
# 10. Download one URL
# ------------------------------------------------------------------------------

download_one <- function(
  dataset_id,
  index,
  url,
  dest_dir,
  probe
) {

  filename <- make_filename(
    dataset_id = dataset_id,
    index = index,
    url = probe$final_url[[1]] %||% url,
    content_type = probe$content_type[[1]],
    content_disposition = probe$content_disposition[[1]]
  )

  dest <- fs::path(
    dest_dir,
    filename
  )

  if (fs::file_exists(dest)) {
    message(
      "  [SKIP] already exists: ",
      dest
    )

    return(
      tibble::tibble(
        downloaded = FALSE,
        local_file = dest,
        error = NA_character_
      )
    )
  }

  message(
    "  [GET] ",
    url
  )

  result <- tryCatch(
    {
      curl::curl_download(
        url = url,
        destfile = dest,
        quiet = FALSE,
        mode = "wb"
      )

      tibble::tibble(
        downloaded = TRUE,
        local_file = dest,
        error = NA_character_
      )
    },
    error = function(e) {
      if (fs::file_exists(dest)) {
        try(
          fs::file_delete(dest),
          silent = TRUE
        )
      }

      tibble::tibble(
        downloaded = FALSE,
        local_file = dest,
        error = conditionMessage(e)
      )
    }
  )

  result
}

# ------------------------------------------------------------------------------
# 11. Process each dataset
# ------------------------------------------------------------------------------

all_manifest_rows <- list()

for (k in seq_len(nrow(datasets))) {

  ds <- datasets[k, ]

  message(
    paste0(
      "\n",
      strrep("=", 78),
      "\nPELGAS / SEANOE ",
      ds$id,
      " — ",
      ds$label,
      "\nDOI: ",
      ds$doi,
      "\nRole: ",
      ds$role,
      "\nKnown period: ",
      ds$known_period,
      "\n",
      strrep("=", 78)
    )
  )

  ds_dir <- fs::path(
    RAW_ROOT,
    paste0(
      ds$id,
      "_",
      ds$label
    )
  )

  fs::dir_create(
    ds_dir,
    recurse = TRUE
  )

  # --------------------------------------------------------------------------
  # Metadata API
  # --------------------------------------------------------------------------

  metadata <- get_seanoe_metadata(
    ds$id
  )

  if (!is.null(metadata)) {
    jsonlite::write_json(
      metadata,
      path = fs::path(
        META_ROOT,
        paste0(
          "seanoe_",
          ds$id,
          "_metadata.json"
        )
      ),
      pretty = TRUE,
      auto_unbox = TRUE,
      null = "null"
    )
  }

  # --------------------------------------------------------------------------
  # DOI resolution
  # --------------------------------------------------------------------------

  landing_url <- resolve_doi(
    ds$doi
  )

  message(
    "Landing page: ",
    landing_url
  )

  # --------------------------------------------------------------------------
  # Discover candidate data links
  # --------------------------------------------------------------------------

  candidates <- build_candidate_table(
    metadata,
    landing_url
  )

  if (nrow(candidates) == 0) {
    warning(
      "No URL candidates found for dataset ",
      ds$id
    )
    next
  }

  candidate_file <- fs::path(
    META_ROOT,
    paste0(
      "seanoe_",
      ds$id,
      "_url_candidates.csv"
    )
  )

  readr::write_csv(
    candidates,
    candidate_file
  )

  message(
    "Candidate URL inventory: ",
    candidate_file
  )

  # We keep candidates that look like actual downloadable resources.
  selected <- candidates |>
    dplyr::filter(score >= 3)

  if (nrow(selected) == 0) {
    warning(
      "No high-confidence data URLs found for dataset ",
      ds$id,
      ". Inspect: ",
      candidate_file
    )
    next
  }

  # --------------------------------------------------------------------------
  # Probe candidates
  # --------------------------------------------------------------------------

  selected_probed <- purrr::map_dfr(
    seq_len(nrow(selected)),
    function(i) {
      p <- probe_url(
        selected$url[[i]]
      )

      dplyr::bind_cols(
        selected[i, , drop = FALSE],
        p
      )
    }
  ) |>
    dplyr::mutate(
      is_html = stringr::str_detect(
        dplyr::coalesce(
          content_type,
          ""
        ),
        regex(
          "text/html",
          ignore_case = TRUE
        )
      ),
      is_attachment = stringr::str_detect(
        dplyr::coalesce(
          content_disposition,
          ""
        ),
        regex(
          "attachment|filename",
          ignore_case = TRUE
        )
      ),
      has_file_extension = stringr::str_detect(
        dplyr::coalesce(
          final_url,
          url
        ),
        regex(
          "\\.(csv|tsv|txt|zip|gz|tar|7z|xlsx|xls|ods|rds|rdata|nc|netcdf|json|xml)(\\?|$)",
          ignore_case = TRUE
        )
      )
    )

  probed_file <- fs::path(
    META_ROOT,
    paste0(
      "seanoe_",
      ds$id,
      "_probed_urls.csv"
    )
  )

  readr::write_csv(
    selected_probed,
    probed_file
  )

  # Actual download criterion:
  # - server explicitly marks it as attachment; OR
  # - recognizable data-file URL; OR
  # - non-HTML content with a strong candidate score.
  to_download <- selected_probed |>
    dplyr::filter(
      !is_html |
        is_attachment |
        has_file_extension
    ) |>
    dplyr::filter(
      status < 400 |
        is.na(status)
    ) |>
    dplyr::distinct(
      dplyr::coalesce(
        final_url,
        url
      ),
      .keep_all = TRUE
    )

  if (nrow(to_download) == 0) {
    warning(
      "Candidates were found but none were confirmed as data files for ",
      ds$id,
      ". Inspect: ",
      probed_file
    )
    next
  }

  message(
    "Confirmed/likely data resources: ",
    nrow(to_download)
  )

  # --------------------------------------------------------------------------
  # Download
  # --------------------------------------------------------------------------

  if (DRY_RUN) {
    message(
      "[DRY RUN] No files downloaded."
    )

    manifest_rows <- to_download |>
      dplyr::mutate(
        dataset_id = ds$id,
        doi = ds$doi,
        dataset_label = ds$label,
        local_file = NA_character_,
        downloaded = FALSE,
        error = NA_character_
      )

  } else {

    download_results <- purrr::map_dfr(
      seq_len(nrow(to_download)),
      function(i) {

        download_url <- (
          to_download$final_url[[i]] %||%
            to_download$url[[i]]
        )

        dl <- download_one(
          dataset_id = ds$id,
          index = i,
          url = download_url,
          dest_dir = ds_dir,
          probe = to_download[i, , drop = FALSE]
        )

        dplyr::bind_cols(
          to_download[i, , drop = FALSE],
          dl
        )
      }
    )

    manifest_rows <- download_results |>
      dplyr::mutate(
        dataset_id = ds$id,
        doi = ds$doi,
        dataset_label = ds$label
      )
  }

  all_manifest_rows[[length(all_manifest_rows) + 1]] <- manifest_rows
}

# ------------------------------------------------------------------------------
# 12. Global manifest
# ------------------------------------------------------------------------------

if (length(all_manifest_rows) > 0) {

  manifest <- dplyr::bind_rows(
    all_manifest_rows
  ) |>
    dplyr::relocate(
      dataset_id,
      doi,
      dataset_label
    )

  manifest_path <- fs::path(
    META_ROOT,
    "pelgas_seanoe_download_manifest.csv"
  )

  readr::write_csv(
    manifest,
    manifest_path
  )

  message(
    "\nGlobal manifest written to:\n  ",
    manifest_path
  )

  if (!DRY_RUN) {

    successful <- manifest |>
      dplyr::filter(
        !is.na(local_file),
        fs::file_exists(local_file)
      )

    message(
      "Downloaded/existing files in manifest: ",
      nrow(successful)
    )

    if (nrow(successful) > 0) {
      message(
        "\nFiles:"
      )

      for (f in unique(successful$local_file)) {
        message(
          "  [OK] ",
          f
        )
      }
    }
  }
}

# ------------------------------------------------------------------------------
# 13. Final scientific notes
# ------------------------------------------------------------------------------

message(
  paste0(
    "\n",
    strrep("=", 78),
    "\nDONE\n",
    strrep("=", 78),
    "\n\n",
    "Priority for PelagicLens:\n",
    "  1) 53389 -> spatial/gridded PELGAS ecosystem and fish information\n",
    "  2) 59809 -> trawl-level biotic observations / species composition\n",
    "  3) 53388 -> population-level biomass/abundance-at-length support\n\n",
    "Target species:\n",
    "  Engraulis encrasicolus\n",
    "  WoRMS AphiaID: 126426\n\n",
    "Do not convert missing observations outside sampled effort into absences.\n",
    "The next step after download is an inventory of actual file names, columns,\n",
    "years, coordinates, species fields, and fish-response variables.\n"
  )
)
