// PAPPA: запись папки образца из C — тот же контракт, что у Python/C++/Go
// (python/pappa/io/sample_store.py + model_file.py, CONTEXT §27):
//   <out_dir>/sample.json                манифест (format pappa-sample v1.0)
//   <out_dir>/sections/00.pappa.json     документ сечения (pappa v2.0)
// Формат повторяет cpp/sample_writer.cpp поле в поле: папки от разных портов
// сравниваются численно (python/studies/verify_port.py).
#include <stdio.h>
#include <string.h>
#include <time.h>

#if defined(_WIN32)
#include <direct.h>
#define PP_MKDIR(p) _mkdir(p)
#else
#include <sys/stat.h>
#define PP_MKDIR(p) mkdir(p, 0755)
#endif

#include "pappa.h"

#define PP_PORT_VERSION "0.1.0"

static void iso_utc_now(char *out, size_t n) {
    time_t t = time(NULL);
    struct tm tmv;
#if defined(_WIN32)
    gmtime_s(&tmv, &t);
#else
    gmtime_r(&t, &tmv);
#endif
    strftime(out, n, "%Y-%m-%dT%H:%M:%SZ", &tmv);
}

static void q(FILE *f, const char *s) {
    fputc('"', f);
    for (; s && *s; ++s) {
        if (*s == '"' || *s == '\\') fputc('\\', f);
        fputc(*s, f);
    }
    fputc('"', f);
}
static void kv_s(FILE *f, const char *k, const char *v, const char *ind) {
    fprintf(f, "%s\"%s\": ", ind, k);
    q(f, v);
}
static void kv_d(FILE *f, const char *k, double v, const char *ind) {
    fprintf(f, "%s\"%s\": %.17g", ind, k, v);
}
static void kv_i(FILE *f, const char *k, int v, const char *ind) {
    fprintf(f, "%s\"%s\": %d", ind, k, v);
}


static int write_section_doc(const char *path, const pp_model *m,
                             const pp_meta *md, double fit_time_ms) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    char created[32];
    iso_utc_now(created, sizeof(created));
    const double sector = 360.0 / (double)m->n_patches;
    const double half_sector = sector / 2.0;

    fputs("{\n", f);
    kv_s(f, "format", "pappa", "  ");   fputs(",\n", f);
    kv_s(f, "version", "2.0", "  ");    fputs(",\n", f);
    kv_s(f, "method", m->n_pits > 0 ? "PitPatchApproximator" : "PatchApproximator",
         "  ");                          fputs(",\n", f);
    kv_s(f, "created", created, "  ");  fputs(",\n", f);
    fputs("  \"software\": {\"language\": \"c\", \"pappa_version\": \""
          PP_PORT_VERSION "\"},\n", f);
    fputs("  \"meta\": {\n", f);
    kv_i(f, "section_id", md->section_id, "    ");  fputs(",\n", f);
    kv_d(f, "height_mm", md->height_mm, "    ");    fputs(",\n", f);
    kv_s(f, "source", md->source ? md->source : "", "    "); fputs(",\n", f);
    kv_s(f, "description", md->description ? md->description : "", "    ");
    fputs("\n  },\n", f);

    fputs("  \"global\": {\n", f);
    fputs("    \"units\": {\"angle\": \"degree\", \"length\": \"mm\"},\n", f);
    kv_i(f, "n_patches", m->n_patches, "    ");          fputs(",\n", f);
    kv_d(f, "half_sector_deg", half_sector, "    ");     fputs(",\n", f);
    kv_d(f, "phase_deg", m->phase_deg, "    ");          fputs(",\n", f);
    kv_d(f, "half_train_deg", half_sector + m->overlap_train, "    "); fputs(",\n", f);
    kv_d(f, "half_use_deg", half_sector + m->overlap_use, "    ");     fputs(",\n", f);
    kv_d(f, "overlap_train_deg", m->overlap_train, "    "); fputs(",\n", f);
    kv_d(f, "overlap_use_deg", m->overlap_use, "    ");     fputs(",\n", f);
    kv_i(f, "deg_min", m->deg_min, "    ");              fputs(",\n", f);
    kv_i(f, "deg_max", m->deg_max, "    ");              fputs(",\n", f);
    kv_s(f, "coord_mode", m->coord_mode ? m->coord_mode : "normalized", "    ");
    fputs(",\n", f);
    kv_d(f, "deg_elbow_tol", m->deg_elbow_tol, "    ");  fputs(",\n", f);
    kv_d(f, "amplitude_scale", m->amplitude_scale, "    ");
    if (m->n_pits > 0) {
        fputs(",\n    \"pit\": {\n", f);
        kv_d(f, "sigma_deg", m->sigma_deg, "      ");       fputs(",\n", f);
        kv_d(f, "core_sigma", m->core_sigma, "      ");     fputs(",\n", f);
        kv_d(f, "window_sigma", m->window_sigma, "      "); fputs(",\n", f);
        kv_d(f, "pit_min_amp", m->pit_min_amp, "      ");   fputs(",\n", f);
        fprintf(f, "      \"tapering\": %s,\n", m->tapering ? "true" : "false");
        fputs("      \"centers_deg\": [", f);
        for (int i = 0; i < m->n_pits; ++i)
            fprintf(f, "%s%.17g", i ? ", " : "", m->pits[i]);
        fputs("]\n    }", f);
    }
    fputs("\n  },\n", f);

    fputs("  \"patches\": [\n", f);
    for (int p = 0; p < m->n_patches; ++p) {
        const pp_patch *pt = &m->patches[p];
        fputs("    {\n", f);
        kv_d(f, "center_deg", pt->center, "      ");  fputs(",\n", f);
        kv_i(f, "degree", pt->degree, "      ");      fputs(",\n", f);
        kv_i(f, "n_points", pt->n_points, "      ");  fputs(",\n", f);
        fputs("      \"coefs\": [", f);
        for (int k = 0; k <= pt->degree; ++k)
            fprintf(f, "%s%.17g", k ? ", " : "", pt->coefs[k]);
        fputs("],\n      \"metrics\": {\n", f);
        kv_d(f, "amplitude_mm", pt->amplitude_mm, "        ");    fputs(",\n", f);
        kv_d(f, "mean_radius_mm", pt->mean_radius_mm, "        "); fputs(",\n", f);
        kv_d(f, "amplitude_norm", pt->amplitude_norm, "        "); fputs(",\n", f);
        kv_d(f, "deg_elbow_tol", m->deg_elbow_tol, "        ");   fputs(",\n", f);
        kv_d(f, "rmse_selected_mm", pt->rmse_selected_mm, "        "); fputs(",\n", f);
        kv_d(f, "rmse_best_mm", pt->rmse_best_mm, "        ");    fputs(",\n", f);
        kv_i(f, "n_train_points", pt->n_points, "        ");
        fputs("\n      },\n      \"stats\": {\n", f);
        kv_d(f, "rmse_mm", pt->rmse_mm, "        ");       fputs(",\n", f);
        kv_d(f, "mae_mm", pt->mae_mm, "        ");         fputs(",\n", f);
        kv_d(f, "max_err_mm", pt->max_err_mm, "        "); fputs(",\n", f);
        kv_d(f, "correlation", pt->correlation, "        ");
        fputs("\n      }", f);
        if (m->n_pits > 0) {
            fputs(",\n      \"pit_terms\": [", f);
            for (int j = 0; j < pt->n_pit; ++j)
                fprintf(f, "%s{\"dx_deg\": %.17g, \"amp\": %.17g}", j ? ", " : "",
                        pt->pit_off[j], pt->pit_amp[j]);
            fputs("]", f);
        }
        fprintf(f, "\n    }%s\n", (p + 1 < m->n_patches) ? "," : "");
    }
    fputs("  ],\n  \"statistics\": {\n", f);
    kv_i(f, "n_points_total", md->n_points_total, "    "); fputs(",\n", f);
    kv_i(f, "n_outliers_removed", md->n_outliers, "    "); fputs(",\n", f);
    kv_d(f, "fit_time_ms", fit_time_ms, "    ");
    fputs("\n  }\n}\n", f);
    fclose(f);
    return 0;
}


int pp_save_sample(const char *out_dir, const char *name, const pp_model *models,
                   const pp_meta *meta, int nsec, double cl_base, double cl_k,
                   int pits, const char *input_csv, const char *description) {
    char dir[1024], sub[1024], manifest[1200];
    snprintf(dir, sizeof(dir), "%s", out_dir);
    PP_MKDIR(dir);
    snprintf(sub, sizeof(sub), "%s/sections", dir);
    PP_MKDIR(sub);

    char created[32];
    iso_utc_now(created, sizeof(created));
    snprintf(manifest, sizeof(manifest), "%s/sample.json", dir);
    FILE *f = fopen(manifest, "wb");
    if (!f) return -1;

    fputs("{\n", f);
    kv_s(f, "format", "pappa-sample", "  ");  fputs(",\n", f);
    kv_s(f, "version", "1.0", "  ");          fputs(",\n", f);
    kv_s(f, "name", name, "  ");              fputs(",\n", f);
    kv_s(f, "created", created, "  ");        fputs(",\n", f);
    fputs("  \"units\": {\"angle\": \"degree\", \"length\": \"mm\"},\n", f);
    fputs("  \"meta\": {\"description\": ", f);
    q(f, description ? description : "");
    fputs("},\n", f);
    if (input_csv && input_csv[0]) {
        fputs("  \"input\": {\"csv\": ", f);
        q(f, input_csv);
        fputs("},\n", f);
    }
    const pp_model *first = (nsec > 0) ? &models[0] : NULL;
    fputs("  \"config\": {\n", f);
    kv_i(f, "n_patches", first ? first->n_patches : 0, "    ");         fputs(",\n", f);
    kv_d(f, "phase_deg", first ? first->phase_deg : 0.0, "    ");        fputs(",\n", f);
    kv_i(f, "deg_min", first ? first->deg_min : 0, "    ");             fputs(",\n", f);
    kv_i(f, "deg_max", first ? first->deg_max : 0, "    ");             fputs(",\n", f);
    kv_d(f, "overlap_train", first ? first->overlap_train : 0.0, "    "); fputs(",\n", f);
    kv_d(f, "overlap_use", first ? first->overlap_use : 0.0, "    ");   fputs(",\n", f);
    kv_d(f, "deg_elbow_tol", first ? first->deg_elbow_tol : 0.0, "    "); fputs(",\n", f);
    fprintf(f, "    \"cleaner\": {\"mode\": \"auto\", \"auto\": "
               "{\"method\": \"iqr\", \"baseline_deg\": %.17g, \"iqr_k\": %.17g}},\n",
            cl_base, cl_k);
    fprintf(f, "    \"pits\": %s", pits ? "true" : "false");
    if (pits && first) {
        fputs(",\n", f);
        kv_d(f, "sigma_deg", first->sigma_deg, "    ");          fputs(",\n", f);
        kv_d(f, "pit_core_sigma", first->core_sigma, "    ");    fputs(",\n", f);
        kv_d(f, "pit_window_sigma", first->window_sigma, "    "); fputs(",\n", f);
        kv_d(f, "pit_min_amp", first->pit_min_amp, "    ");      fputs(",\n", f);
        fprintf(f, "    \"tapering\": %s", first->tapering ? "true" : "false");
    }
    fputs(",\n    \"detector\": null\n  },\n  \"sections\": [\n", f);

    for (int i = 0; i < nsec; ++i) {
        char file[64], path[1200];
        snprintf(file, sizeof(file), "sections/%02d.pappa.json", i);
        snprintf(path, sizeof(path), "%s/%s", dir, file);
        if (write_section_doc(path, &models[i], &meta[i], meta[i].fit_time_ms) != 0) {
            fclose(f);
            return -1;
        }
        fputs("    {\n", f);
        kv_i(f, "index", i, "      ");                        fputs(",\n", f);
        kv_i(f, "section_id", meta[i].section_id, "      ");  fputs(",\n", f);
        kv_d(f, "height_mm", meta[i].height_mm, "      ");    fputs(",\n", f);
        kv_s(f, "file", file, "      ");                      fputs(",\n", f);
        kv_i(f, "n_points", meta[i].n_points_total, "      "); fputs(",\n", f);
        kv_i(f, "n_outliers", meta[i].n_outliers, "      ");
        fprintf(f, "\n    }%s\n", (i + 1 < nsec) ? "," : "");
    }
    fputs("  ]\n}\n", f);
    fclose(f);
    return 0;
}
