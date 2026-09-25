function res = cleaner_clean_iqr(angles, radii, o)
% Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным
% фильтром по кольцу, считаем остаток и его робастный масштаб; порог — усы
% Тьюки (k · IQR). Повторяет AutoOutlierCleaner референса Python.
%
% Возвращает структуру с полями mask (true — точка выброшена), n_outliers,
% window (ширина окна снятия формы в точках; 0 — очистка отключена).
  if nargin < 3
    o = cleaner_options();
  end
  angles = angles(:);
  radii = radii(:);
  n = numel(radii);
  res = struct('mask', false(n, 1), 'n_outliers', 0, 'window', 0);
  if n < o.min_points
    return;
  end

  w = signal_window_points(angles, o.baseline_deg);
  base = signal_median_filter(radii, w);
  r = radii - base;

  center = signal_median2(r);
  spread = signal_iqr2(r);
  if spread > 1e-12
    denom = spread;
  else
    denom = 1.0;        % защита референса: при нулевом остатке порог 3 мм
  end

  sev = abs(r - center) / denom;
  mask = sev > o.iqr_k;
  flagged = sum(mask);

  % Предохранитель: не выбрасываем больше max_removed_frac точек.
  cap = floor(o.max_removed_frac * n);
  if cap > 0 && cap < n && flagged > cap
    kept = sort(sev(mask));
    level = kept(numel(kept) - cap + 1);
    mask = mask & (sev >= level);
    flagged = sum(mask);
  end
  res = struct('mask', mask, 'n_outliers', flagged, 'window', w);
end
