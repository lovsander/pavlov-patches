function w = signal_odd_window(window, n)
% Ширина окна в точках: нечётная, не меньше 3 и не шире массива.
  if mod(window, 2) == 0
    w = window + 1;
  else
    w = window;
  end
  if w < 3
    w = 3;
  end
  if w > n
    if mod(n, 2) == 1
      w = n;
    else
      w = n - 1;
    end
  end
end
