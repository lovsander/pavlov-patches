using System;
using System.Globalization;

namespace Pappa
{
    /// <summary>
    /// Форматирование чисел и строк — всегда InvariantCulture.
    /// Локаль машины не должна влиять ни на документы, ни на диагностику:
    /// ru-RU дала бы "8,73e-11" и запятую как разделитель дробной части.
    /// </summary>
    public static class Fmt
    {
        public static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        /// <summary>Аналог C-шного "%.{digits}e": строчная 'e', как у numpy/Python.</summary>
        public static string E(double v, int digits = 2)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return v.ToString(Inv);
            string spec = digits <= 0 ? "0e+00" : "0." + new string('0', digits) + "e+00";
            return v.ToString(spec, Inv);
        }

        /// <summary>Аналог "%.1f".</summary>
        public static string F1(double v) => v.ToString("0.0", Inv);

        /// <summary>Строка вида "{0,-46} {1,-5} {2}" с выравниванием (как printf).</summary>
        public static string Pad(string s, int width)
        {
            if (s == null) s = "";
            return width <= 0 ? s : s.PadRight(width);
        }

        public static string Bool(bool v) => v ? "true" : "false";
    }
}
