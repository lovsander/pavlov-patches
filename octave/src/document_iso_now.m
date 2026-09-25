function s = document_iso_now()
% Отметка времени UTC в ISO 8601 (без долей секунды) — как в остальных портах.
%
% ЛОВУШКА OCTAVE: clock()/localtime() возвращают МЕСТНОЕ время, поэтому берём
% time() (секунды от эпохи, UTC по определению) и gmtime().
  secs = floor(time());
  days = floor(secs / 86400);
  rem_s = secs - days * 86400;
  ymd = civil_from_days(days);
  s = sprintf('%04d-%02d-%02dT%02d:%02d:%02dZ', ymd(1), ymd(2), ymd(3), ...
              floor(rem_s / 3600), floor(mod(rem_s, 3600) / 60), mod(rem_s, 60));
end

function ymd = civil_from_days(z0)
% Алгоритм Говарда Хиннанта: число дней с 1970-01-01 -> год, месяц, день.
  z = z0 + 719468;
  era = floor(z / 146097);
  doe = z - era * 146097;
  yoe = floor((doe - floor(doe / 1460) + floor(doe / 36524) - floor(doe / 146096)) / 365);
  y = yoe + era * 400;
  doy = doe - (365 * yoe + floor(yoe / 4) - floor(yoe / 100));
  mp = floor((5 * doy + 2) / 153);
  d = doy - floor((153 * mp + 2) / 5) + 1;
  m = mp + 3;
  if m > 12
    m = m - 12;
  end
  if m <= 2
    yy = y + 1;
  else
    yy = y;
  end
  ymd = [yy, m, d];
end
