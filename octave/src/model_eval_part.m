function out = model_eval_part(m, angles, part)
% Контур: нормированное smoothstep-смешивание патчей (partition of unity).
% part = 'total' | 'poly' | 'pit' — какие члены включать.
%
% Это ОСТАВШИЙСЯ цикл по точкам: 6000 углов × 7 патчей у Octave в цикле идут
% заметное время, но полный контур нужен только векторам конформанса и тестам
% (пайплайн контур не вычисляет), поэтому читаемость здесь важнее векторизации.
  if nargin < 3
    part = 'total';
  end
  if ~m.is_fitted
    error('model_eval_part: model is not fitted');
  end
  hu = model_half_use(m);
  ht = model_half_train(m);
  raw = strcmp(m.options.coord_mode, 'raw');
  angles = angles(:);
  out = zeros(numel(angles), 1);
  for k = 1:numel(angles)
    a = angles(k);
    sum_wv = 0;
    sum_w = 0;
    for pi = 1:numel(m.patches)
      p = m.patches{pi};
      w = model_weight(m, signal_circ_dist(a, p.center_deg), hu);
      if w <= 0
        continue;
      end
      dx = signal_circ_local(a, p.center_deg);
      if raw
        x = dx;
      else
        x = dx / ht;
      end
      v = 0;
      if ~strcmp(part, 'pit')
        v = v + linalg_polyval(p.coefs, x);
      end
      if ~strcmp(part, 'poly')
        for j = 1:numel(p.pit_offsets_deg)
          v = v + p.pit_coefs(j) * model_pit_shape_deg(m, abs(x * ht - p.pit_offsets_deg(j)));
        end
      end
      sum_wv = sum_wv + w * v;
      sum_w = sum_w + w;
    end
    if sum_w > 0
      out(k) = sum_wv / sum_w;
    else
      out(k) = 0;
    end
  end
end
