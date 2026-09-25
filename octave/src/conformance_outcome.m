function r = conformance_outcome(ok, detail, notes)
% Результат проверки одного вектора: ok / detail / notes.
  if nargin < 3
    notes = {};
  end
  r = struct();
  r.ok = logical(ok);
  r.detail = detail;
  r.notes = notes;
end
