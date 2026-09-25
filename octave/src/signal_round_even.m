function y = signal_round_even(x)
% Round half to even (IEC 60559) — like Python round() / C rint().
%
% ЛОВУШКА OCTAVE: round() здесь округляет половину ОТ НУЛЯ (round(2.5) == 3),
% поэтому для ширин окон, значения которых референс округляет «половина к
% чётному», его брать нельзя. printf('%.0f') в Octave, наоборот, даёт
% половину к чётному — но вернуть из него число нельзя, только текст.
  y = zeros(size(x));
  for k = 1:numel(x)
    v = x(k);
    if ~isfinite(v)
      y(k) = v;
      continue;
    end
    f = floor(v);
    d = v - f;
    if d > 0.5
      y(k) = f + 1;
    elseif d < 0.5
      y(k) = f;
    elseif mod(f, 2) == 0
      y(k) = f;            % ничья: чётный сосед снизу
    else
      y(k) = f + 1;        % ничья: чётный сосед сверху
    end
  end
end
