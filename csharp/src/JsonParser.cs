using System;
using System.Collections.Generic;
using System.Text;

namespace Pappa
{
    /// <summary>
    /// Рекурсивный спуск по JSON — ровно столько, сколько нужно векторам и документам.
    /// Числа читаются как double (целые тоже), как это делает Python-референс.
    /// </summary>
    internal sealed class JsonParser
    {
        private readonly string s;
        private int i;

        public JsonParser(string text)
        {
            s = text;
            i = 0;
        }

        public void Ws()
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        public object Value()
        {
            switch (s[i])
            {
                case '{': return ObjectBody();
                case '[': return ArrayBody();
                case '"': return StrBody();
                case 't': Expect("true"); return true;
                case 'f': Expect("false"); return false;
                case 'n': Expect("null"); return null;
                default: return Number();
            }
        }

        private void Expect(string lit)
        {
            if (i + lit.Length > s.Length || string.CompareOrdinal(s, i, lit, 0, lit.Length) != 0)
                throw new FormatException("JSON: ожидался литерал " + lit + " в позиции " + i);
            i += lit.Length;
        }

        private Dictionary<string, object> ObjectBody()
        {
            var m = new Dictionary<string, object>();
            i++;                                   // {
            Ws();
            if (s[i] == '}') { i++; return m; }
            while (true)
            {
                Ws();
                string k = StrBody();
                Ws();
                if (s[i] != ':') throw new FormatException("JSON: ожидалось ':' в позиции " + i);
                i++;
                Ws();
                m[k] = Value();
                Ws();
                char c = s[i++];
                if (c == '}') return m;
                if (c != ',') throw new FormatException("JSON: ожидалась ',' или '}'");
            }
        }

        private List<object> ArrayBody()
        {
            var a = new List<object>();
            i++;                                   // [
            Ws();
            if (s[i] == ']') { i++; return a; }
            while (true)
            {
                Ws();
                a.Add(Value());
                Ws();
                char c = s[i++];
                if (c == ']') return a;
                if (c != ',') throw new FormatException("JSON: ожидалась ',' или ']'");
            }
        }

        private string StrBody()
        {
            if (s[i] != '"') throw new FormatException("JSON: ожидалась строка в позиции " + i);
            i++;
            var b = new StringBuilder();
            while (true)
            {
                char c = s[i++];
                if (c == '"') return b.ToString();
                if (c != '\\') { b.Append(c); continue; }
                char e = s[i++];
                switch (e)
                {
                    case 'n': b.Append('\n'); break;
                    case 't': b.Append('\t'); break;
                    case 'r': b.Append('\r'); break;
                    case 'b': b.Append('\b'); break;
                    case 'f': b.Append('\f'); break;
                    case 'u':
                        b.Append((char)Convert.ToInt32(s.Substring(i, 4), 16));
                        i += 4;
                        break;
                    default: b.Append(e); break;
                }
            }
        }

        private double Number()
        {
            int start = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            string t = s.Substring(start, i - start);
            if (!double.TryParse(t, System.Globalization.NumberStyles.Float, Fmt.Inv, out double v))
                throw new FormatException("JSON: плохое число " + t);
            return v;
        }
    }
}
