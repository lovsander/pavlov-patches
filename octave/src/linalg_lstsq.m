function x = linalg_lstsq(a_in, b_in)
% МНК A·x ≈ b (A — m×n, m >= n) через QR отражениями Хаусхолдера.
%
% Почему не a \ b и не qr(): у них LAPACK-путь со своим pivoting и своей
% псевдообработкой вырожденных столбцов — коэффициенты разошлись бы с
% остальными портами сильнее, чем допускает вектор модели (1e-9 отн.).
% Вход не портится (копия a_in).
  [m, n] = size(a_in);
  if m == 0
    error('linalg_lstsq: empty matrix');
  end
  if numel(b_in) ~= m
    error('linalg_lstsq: lengths of A and b differ');
  end
  if m < n
    error('linalg_lstsq: need m >= n');
  end
  a = double(a_in);
  b = double(b_in(:));

  for k = 1:n
    nrm = sqrt(sum(a(k:m, k) .^ 2));
    if nrm < 1e-300
      continue;
    end
    if a(k, k) > 0
      alpha = -nrm;
    else
      alpha = nrm;
    end
    v = zeros(m, 1);
    v(k:m) = a(k:m, k);
    v(k) = v(k) - alpha;
    vnorm2 = sum(v(k:m) .^ 2);
    if vnorm2 < 1e-300
      continue;
    end
    for j = k:n
      cc = 2 * sum(v(k:m) .* a(k:m, j)) / vnorm2;
      a(k:m, j) = a(k:m, j) - cc * v(k:m);
    end
    cb = 2 * sum(v(k:m) .* b(k:m)) / vnorm2;
    b(k:m) = b(k:m) - cb * v(k:m);
  end

  x = zeros(n, 1);
  for i = n:-1:1
    s = b(i);
    if i < n
      % ЛОВУШКА OCTAVE: писать `sum(a(i, k:n) .* x(k:n))` здесь НЕЛЬЗЯ — строка
      % 1×m, умноженная поэлементно на столбец m×1, в Octave раскрывается в
      % матрицу m×m (implicit expansion), а не даёт ошибку формы. Произведение
      % строка×столбец даёт скаляр и однозначно.
      s = s - a(i, (i + 1):n) * x((i + 1):n);
    end
    d = a(i, i);
    if abs(d) < 1e-300
      error('linalg_lstsq: singular system');
    end
    x(i) = s / d;
  end
end
