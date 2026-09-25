function tf = model_has_pits(m)
% Есть ли в модели ямные термы (влияет на имя метода и на ключ pit_terms).
  tf = ~isempty(m.pits);
end
