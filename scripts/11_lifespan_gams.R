#!/usr/bin/env Rscript
# Step 6 - Lifespan models (hypotheses H1-H4): how each brain volume changes with age.
#
# For each volume: a GAM with a smooth of age (thin-plate spline, k = 5, REML) plus sex,
# site and intracranial volume (pre-registration, "Lifespan models"). Run on the
# ComBat-harmonised volumes from scripts/10_harmonise.py.
#
# Usage, from the project folder:
#   Rscript scripts/11_lifespan_gams.R --shuffled   # blind analysis: results are meaningless
#   Rscript scripts/11_lifespan_gams.R              # real data, after unblinding
#
# Analyses (main model plus the sensitivity analyses):
#   primary      reviewed QC, harmonised volumes, ICV-adjusted          (confirmatory)
#   exclude_1s   scans rated 1 excluded too                             (pre-registered)
#   no_iop       IOP site left out                                      (pre-registered)
#   no_combat    raw volumes instead of harmonised                      (pre-registered)
#   no_icv       without the intracranial volume covariate              (pre-registered)
#   include_wb2  whole-brain fails kept                                 (README, 6 Oct 2026)
#   first_pass   first-pass QC exclusions                               (README, 6 Oct 2026)
#
# For each analysis and volume it reports the age smooth's F-test and, from 2,000 draws
# of the model's coefficients, estimates with 95% intervals of:
#   total_change      fitted volume at the oldest age minus the youngest (cm3)
#   slope_before_60   mean change per decade from the youngest age to 60 (cm3/decade)
#   slope_after_60    mean change per decade from 60 to the oldest age (cm3/decade)
#   peak_age          age at which the fitted curve is highest
# Curves are evaluated for a female participant at the reference site with average ICV;
# with no interactions in the model, the curve's shape is the same for everyone.
#
# Hypothesis checks (written before any real result, applied to every analysis):
#   H1 grey matter declines:        p < .05 and total_change < 0
#   H2 white matter inverted U:     p < .05, peak at least 5 years inside the age range,
#                                   and slope_after_60 < 0
#   H3 CSF rises, faster later:     p < .05, total_change > 0, slope_after_60 > slope_before_60
#   H4 hippocampus and thalamus     FDR-corrected p < .05 (Benjamini-Hochberg over the 15
#      decline, steeper after 60:   FIRST structures), total_change < 0,
#                                   slope_after_60 < slope_before_60; checked for each of
#                                   left/right hippocampus and thalamus
# A hypothesis is called robust if its check holds in every analysis.
# Exploratory: sex-by-age interaction (primary analysis), reported as such.
#
# Outputs in results/<shuffled|real>/: gam_results.csv, gam_hypotheses.csv,
# gam_sex_interaction.csv, fig_lifespan_whole_brain.png, fig_lifespan_subcortical.png,
# session_info.txt

suppressPackageStartupMessages({
  library(mgcv)
  library(ggplot2)
})

# ---- Setup -------------------------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
SHUFFLED <- "--shuffled" %in% args
script_path <- sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE))
PROJECT <- normalizePath(file.path(dirname(script_path), ".."))
stem <- if (SHUFFLED) "analysis_shuffled" else "analysis_dataset"
infile <- file.path(PROJECT, "data", paste0(stem, "_harmonised.csv"))
if (!file.exists(infile)) {
  stop("Can't find ", infile, ". Run scripts/09_build_dataset.py and scripts/10_harmonise.py",
       if (SHUFFLED) " with --shuffled" else "", " first.")
}
OUT <- file.path(PROJECT, "results", if (SHUFFLED) "shuffled" else "real")
dir.create(OUT, recursive = TRUE, showWarnings = FALSE)

WHOLE <- c("gm", "wm", "csf")
SUB <- c("L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
         "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem")
LABELS <- c(gm = "Grey matter", wm = "White matter", csf = "CSF",
            L_Thal = "L thalamus", L_Caud = "L caudate", L_Puta = "L putamen",
            L_Pall = "L pallidum", L_Hipp = "L hippocampus", L_Amyg = "L amygdala",
            L_Accu = "L accumbens", R_Thal = "R thalamus", R_Caud = "R caudate",
            R_Puta = "R putamen", R_Pall = "R pallidum", R_Hipp = "R hippocampus",
            R_Amyg = "R amygdala", R_Accu = "R accumbens", BrStem = "Brainstem")
NSIM <- 2000
set.seed(42)

ANALYSES <- list(
  primary     = list(variant = "primary",     suffix = "_h", icv = TRUE),
  exclude_1s  = list(variant = "exclude_1s",  suffix = "_h", icv = TRUE),
  no_iop      = list(variant = "no_iop",      suffix = "_h", icv = TRUE),
  no_combat   = list(variant = "primary",     suffix = "",   icv = TRUE),
  no_icv      = list(variant = "primary",     suffix = "_h", icv = FALSE),
  include_wb2 = list(variant = "include_wb2", suffix = "_h", icv = TRUE),
  first_pass  = list(variant = "first_pass",  suffix = "_h", icv = TRUE)
)

all_data <- read.csv(infile, stringsAsFactors = FALSE)
if (!all(as.logical(all_data$shuffled) == SHUFFLED)) {
  stop("The data file's 'shuffled' flag doesn't match the --shuffled option.")
}

prep <- function(variant) {
  d <- all_data[all_data$variant == variant, ]
  d$sex <- factor(d$sex, levels = c("female", "male"))
  d$site <- factor(d$site)
  d$icv_l <- d$icv / 1e6                     # intracranial volume in litres
  d
}

# ---- Model fitting and description ---------------------------------------------------------
fit_gam <- function(d, column, use_icv) {
  dd <- d[!is.na(d[[column]]), ]
  dd$vol <- dd[[column]] / 1000              # mm3 -> cm3
  rhs <- "s(age, k = 5, bs = 'tp') + sex"
  if (nlevels(droplevels(dd$site)) > 1) rhs <- paste(rhs, "+ site")
  if (use_icv) rhs <- paste(rhs, "+ icv_l")
  m <- gam(as.formula(paste("vol ~", rhs)), data = dd, method = "REML")
  list(m = m, d = droplevels(dd))
}

draw_coefs <- function(m, n) {
  # Multivariate normal draws of the coefficients (smoothing-parameter uncertainty included)
  b <- coef(m)
  V <- vcov(m, unconditional = TRUE)
  e <- eigen(V, symmetric = TRUE)
  A <- e$vectors %*% diag(sqrt(pmax(e$values, 0)), nrow = length(b))
  b + A %*% matrix(rnorm(length(b) * n), nrow = length(b))
}

reference_grid <- function(dd, ages) {
  data.frame(age = ages,
             sex = factor("female", levels = levels(dd$sex)),
             site = factor(levels(dd$site)[1], levels = levels(dd$site)),
             icv_l = mean(dd$icv_l))
}

describe <- function(fit) {
  m <- fit$m
  dd <- fit$d
  lo <- ceiling(min(dd$age))
  hi <- floor(max(dd$age))
  grid <- reference_grid(dd, seq(lo, hi, by = 0.5))
  Xp <- predict(m, grid, type = "lpmatrix")
  est <- as.vector(Xp %*% coef(m))
  sims <- Xp %*% draw_coefs(m, NSIM)
  at <- function(a) which.min(abs(grid$age - a))
  a60 <- min(max(60, lo + 1), hi - 1)
  summarise_q <- function(point, draws) {
    c(point, quantile(draws, c(0.025, 0.975), names = FALSE))
  }
  total  <- summarise_q(est[at(hi)] - est[at(lo)], sims[at(hi), ] - sims[at(lo), ])
  before <- summarise_q((est[at(a60)] - est[at(lo)]) / ((a60 - lo) / 10),
                        (sims[at(a60), ] - sims[at(lo), ]) / ((a60 - lo) / 10))
  after  <- summarise_q((est[at(hi)] - est[at(a60)]) / ((hi - a60) / 10),
                        (sims[at(hi), ] - sims[at(a60), ]) / ((hi - a60) / 10))
  peak   <- summarise_q(grid$age[which.max(est)], grid$age[apply(sims, 2, which.max)])
  st <- summary(m)$s.table
  data.frame(n = nrow(dd), age_min = lo, age_max = hi,
             edf = st[1, "edf"], F = st[1, "F"], p = st[1, "p-value"],
             total_change = total[1], total_change_lo = total[2], total_change_hi = total[3],
             slope_before_60 = before[1], slope_before_60_lo = before[2],
             slope_before_60_hi = before[3],
             slope_after_60 = after[1], slope_after_60_lo = after[2],
             slope_after_60_hi = after[3],
             peak_age = peak[1], peak_age_lo = peak[2], peak_age_hi = peak[3],
             mean_volume = mean(dd$vol))
}

# ---- Run every analysis ----------------------------------------------------------------------
results <- list()
fits_primary <- list()
for (a in names(ANALYSES)) {
  spec <- ANALYSES[[a]]
  d <- prep(spec$variant)
  for (s in c(WHOLE, SUB)) {
    fit <- fit_gam(d, paste0(s, spec$suffix), spec$icv)
    if (a == "primary") fits_primary[[s]] <- fit
    results[[length(results) + 1]] <- cbind(analysis = a, structure = s, describe(fit))
  }
  cat(sprintf("  %-12s done\n", a))
}
res <- do.call(rbind, results)

# FDR over the 15 FIRST structures, separately within each analysis
res$p_fdr <- NA_real_
for (a in names(ANALYSES)) {
  i <- res$analysis == a & res$structure %in% SUB
  res$p_fdr[i] <- p.adjust(res$p[i], method = "BH")
}
write.csv(res, file.path(OUT, "gam_results.csv"), row.names = FALSE)

# ---- Hypothesis checks -----------------------------------------------------------------------
check <- function(r, h) {
  with(r, switch(h,
    H1 = p < 0.05 & total_change < 0,
    H2 = p < 0.05 & peak_age >= age_min + 5 & peak_age <= age_max - 5 & slope_after_60 < 0,
    H3 = p < 0.05 & total_change > 0 & slope_after_60 > slope_before_60,
    H4 = p_fdr < 0.05 & total_change < 0 & slope_after_60 < slope_before_60))
}
HYP <- list(H1 = "gm", H2 = "wm", H3 = "csf", H4 = c("L_Hipp", "R_Hipp", "L_Thal", "R_Thal"))
hyp_rows <- list()
for (h in names(HYP)) {
  for (s in HYP[[h]]) {
    row <- data.frame(hypothesis = h, structure = s)
    for (a in names(ANALYSES)) row[[a]] <- check(res[res$analysis == a & res$structure == s, ], h)
    row$robust <- all(unlist(row[names(ANALYSES)]))
    hyp_rows[[length(hyp_rows) + 1]] <- row
  }
}
hyp <- do.call(rbind, hyp_rows)
write.csv(hyp, file.path(OUT, "gam_hypotheses.csv"), row.names = FALSE)

# ---- Exploratory: sex-by-age interaction (primary analysis) -------------------------------
sex_rows <- list()
for (s in c(WHOLE, SUB)) {
  dd <- fits_primary[[s]]$d
  dd$sex_o <- ordered(dd$sex, levels = c("female", "male"))
  m2 <- gam(vol ~ sex_o + s(age, k = 5, bs = "tp") + s(age, by = sex_o, k = 5, bs = "tp") +
              site + icv_l, data = dd, method = "REML")
  st <- summary(m2)$s.table
  sex_rows[[s]] <- data.frame(structure = s, edf = st[2, "edf"], F = st[2, "F"],
                              p = st[2, "p-value"])
}
sexint <- do.call(rbind, sex_rows)
sexint$p_fdr <- NA_real_
sexint$p_fdr[sexint$structure %in% SUB] <- p.adjust(sexint$p[sexint$structure %in% SUB], "BH")
write.csv(sexint, file.path(OUT, "gam_sex_interaction.csv"), row.names = FALSE)

# ---- Figures (primary analysis) ----------------------------------------------------------------
curve_and_points <- function(s) {
  m <- fits_primary[[s]]$m
  dd <- fits_primary[[s]]$d
  grid <- reference_grid(dd, seq(ceiling(min(dd$age)), floor(max(dd$age)), by = 0.5))
  p <- predict(m, grid, se.fit = TRUE)
  curve <- data.frame(structure = s, age = grid$age, fit = p$fit,
                      lo = p$fit - 1.96 * p$se.fit, hi = p$fit + 1.96 * p$se.fit)
  # Points adjusted to the same reference sex, site and ICV as the curve
  ref <- reference_grid(dd, dd$age)
  pts <- data.frame(structure = s, age = dd$age,
                    vol = dd$vol - predict(m, dd) + predict(m, ref))
  list(curve = curve, pts = pts)
}
lifespan_plot <- function(structures, ncol, file, width, height) {
  parts <- lapply(structures, curve_and_points)
  curves <- do.call(rbind, lapply(parts, `[[`, "curve"))
  pts <- do.call(rbind, lapply(parts, `[[`, "pts"))
  for (df in c("curves", "pts")) {
    x <- get(df)
    x$structure <- factor(LABELS[x$structure], levels = LABELS[structures])
    assign(df, x)
  }
  g <- ggplot() +
    geom_point(data = pts, aes(age, vol), size = 0.7, alpha = 0.35, colour = "grey30") +
    geom_ribbon(data = curves, aes(age, ymin = lo, ymax = hi), fill = "#2f6db5", alpha = 0.25) +
    geom_line(data = curves, aes(age, fit), colour = "#2f6db5", linewidth = 0.9) +
    facet_wrap(~ structure, scales = "free_y", ncol = ncol) +
    scale_x_continuous(breaks = seq(20, 80, 10)) +
    labs(x = "Age (years)", y = expression("Volume (cm"^3*"), adjusted for sex, site and ICV"),
         title = if (SHUFFLED) "BLIND ANALYSIS - shuffled data, results are meaningless"
                 else "Brain volumes across the lifespan (IXI)") +
    theme_bw(base_size = 11) +
    theme(plot.title = element_text(colour = if (SHUFFLED) "red3" else "black"))
  ggsave(file, g, width = width, height = height, dpi = 150)
}
lifespan_plot(WHOLE, 3, file.path(OUT, "fig_lifespan_whole_brain.png"), 10, 3.6)
lifespan_plot(SUB, 5, file.path(OUT, "fig_lifespan_subcortical.png"), 13, 8)

writeLines(capture.output(sessionInfo()), file.path(OUT, "session_info.txt"))

# ---- Console summary -----------------------------------------------------------------------------
cat("\n", if (SHUFFLED) "BLIND ANALYSIS (shuffled data) - results are meaningless" else "REAL DATA",
    "\n", sep = "")
prim <- res[res$analysis == "primary", ]
cat(sprintf("Primary analysis: %d models; age effect p < .05 in %d of 18 (FDR-corrected for subcortical)\n",
            nrow(prim), sum(ifelse(prim$structure %in% SUB, prim$p_fdr, prim$p) < 0.05)))
if (SHUFFLED) cat("Expected on shuffled data: about 1 of 18 or fewer, by chance alone.\n")
cat("\nHypothesis checks (TRUE = consistent with the prediction):\n")
print(hyp, row.names = FALSE)
cat("\nSaved results and figures in ", OUT, "\n", sep = "")
