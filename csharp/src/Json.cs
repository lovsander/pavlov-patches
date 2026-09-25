using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Pappa
{
    /// <summary>
    /// Минимальный JSON: разбор и запись без внешних зависимостей.
    /// Объект -> Dictionary&lt;string, object&gt;, массив -> List&lt;object&gt;,
    /// число -> double, строка -> string, литералы -> bool/null.
    /// </summary>
    public static class Json
    {
        public static object Parse(string text)
        {
            var p = new JsonParser(text);
            p.Ws();
            return p.Value();
        }

        public static Dictionary<string, object> ParseObject(string text) => Obj(Parse(text));

        // ---------- доступ к разобранному ----------

        public static Dictionary<string, object> Obj(object o) => (Dictionary<string, object>)o;

        public static List<object> Arr(object o) => (List<object>)o;

        public static object Get(Dictionary<string, object> m, string key) =>
            m.TryGetValue(key, out var v) ? v : null;

        public static bool Has(Dictionary<string, object> m, string key) => m.ContainsKey(key);

        public static double Dbl(Dictionary<string, object> m, string k) => (double)Get(m, k);

        public static double Dbl(Dictionary<string, object> m, string k, double def)
        {
            var v = Get(m, k);
            return v is double d ? d : def;
        }

        public static int Int(Dictionary<string, object> m, string k) => (int)(double)Get(m, k);

        public static int Int(Dictionary<string, object> m, string k, int def)
        {
            var v = Get(m, k);
            return v is double d ? (int)d : def;
        }

        public static string Str(Dictionary<string, object> m, string k) => (string)Get(m, k);

        public static bool Bool(Dictionary<string, object> m, string k, bool def)
        {
            var v = Get(m, k);
            return v is bool b ? b : def;
        }

        public static double[] Doubles(Dictionary<string, object> m, string k)
        {
            var a = Arr(Get(m, k));
            var outp = new double[a.Count];
            for (int i = 0; i < a.Count; i++) outp[i] = (double)a[i];
            return outp;
        }

        public static int[] Ints(Dictionary<string, object> m, string k)
        {
            var a = Arr(Get(m, k));
            var outp = new int[a.Count];
            for (int i = 0; i < a.Count; i++) outp[i] = (int)(double)a[i];
            return outp;
        }

        /// <summary>
        /// Число в документе: целые — без дробной части, иначе shortest round-trip
        /// (.NET Core 3.0+ печатает кратчайшую строку, которая читается обратно).
        /// Очень большие/малые значения уходят в экспоненциальную форму "1E-12" —
        /// это валидный JSON, Python его читает.
        /// </summary>
        public static string Num(double v)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return "0";
            if (v == Math.Round(v, MidpointRounding.ToEven) && Math.Abs(v) < 1e15)
                return ((long)v).ToString(Fmt.Inv);
            return v.ToString("R", Fmt.Inv);
        }

        public static string Escape(string s)
        {
            var b = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': b.Append("\\\""); break;
                    case '\\': b.Append("\\\\"); break;
                    case '\n': b.Append("\\n"); break;
                    case '\r': b.Append("\\r"); break;
                    case '\t': b.Append("\\t"); break;
                    default: b.Append(c); break;
                }
            }
            return b.ToString();
        }
    }
}
