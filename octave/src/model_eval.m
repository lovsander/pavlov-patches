function y = model_eval(m, angles)
% Полный контур модели (° → мм).
  y = model_eval_part(m, angles, 'total');
end
