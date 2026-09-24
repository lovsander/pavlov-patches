#ifndef PATCH_APPROXIMATOR_H
#define PATCH_APPROXIMATOR_H

#include <vector>

struct Patch {
    double center;
    double half_sector;
    double half_train;
    double half_use;
    std::vector<double> coefs;
    int degree;
    int n_points;
};

class PatchApproximator {
private:
    int n_patches;
    int deg_min, deg_max;
    double amplitude_scale, overlap_train, overlap_use, half_sector;
    std::vector<double> centers;
    std::vector<Patch> patches;

    double smoothstep(double t) const;
    double polyval(const std::vector<double>& coefs, double x_norm) const;
    double percentile(std::vector<double> v, double p) const;
    std::vector<double> polyfit(const std::vector<double>& x_norm,
                                const std::vector<double>& y,
                                int deg) const;
    int estimate_degree(const std::vector<double>& angles,
                        const std::vector<double>& radii,
                        double center) const;

public:
    PatchApproximator(int n_patches = 8, int deg_min = 4, int deg_max = 14,
                      double amplitude_scale = 180.0,
                      double overlap_train = 15.0,
                      double overlap_use = 5.0);

    void fit(const std::vector<double>& angles, const std::vector<double>& radii);
    std::vector<double> eval(const std::vector<double>& eval_angles) const;
    std::vector<int> get_degrees() const;
};

#endif // PATCH_APPROXIMATOR_H