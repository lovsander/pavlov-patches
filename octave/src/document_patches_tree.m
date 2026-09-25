function arr = document_patches_tree(m)
% Массив «patches» для документа сечения (массив ячеек структур).
%
% Ключ pit_terms стоит у КАЖДОГО патча, когда модель с ямами, в том числе как
% пустой список (массив ячеек нулевой длины): так ждёт загрузчик Python.
  arr = cell(1, numel(m.patches));
  has_pits = model_has_pits(m);
  for i = 1:numel(m.patches)
    p = m.patches{i};
    t = struct();
    t.center_deg = p.center_deg;
    t.degree = p.degree;
    t.n_points = p.n_points;
    t.coefs = p.coefs(:)';
    t.metrics = struct('amplitude_mm', p.metrics.amplitude_mm, ...
                       'mean_radius_mm', p.metrics.mean_radius_mm, ...
                       'amplitude_norm', p.metrics.amplitude_norm, ...
                       'deg_elbow_tol', p.metrics.deg_elbow_tol, ...
                       'rmse_selected_mm', p.metrics.rmse_selected_mm, ...
                       'rmse_best_mm', p.metrics.rmse_best_mm, ...
                       'n_train_points', p.metrics.n_train_points);
    t.stats = struct('rmse_mm', p.stats.rmse_mm, 'mae_mm', p.stats.mae_mm, ...
                     'max_err_mm', p.stats.max_err_mm, ...
                     'correlation', p.stats.correlation);
    if has_pits
      terms = cell(1, numel(p.pit_offsets_deg));
      for j = 1:numel(p.pit_offsets_deg)
        terms{j} = struct('dx_deg', p.pit_offsets_deg(j), ...
                          'amp', p.pit_coefs(j));
      end
      t.pit_terms = terms;
    end
    arr{i} = t;
  end
end
