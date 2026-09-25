"""
    Pappa.Json

Минимальный JSON: разбор и запись без внешних пакетов.
Объекты — `Dict{String,Any}`, массивы — `Vector{Any}`, числа — `Float64`.
"""
module Json

export json_parse, json_num, json_esc, read_text, write_text,
       jget, jdbl, jdbl_or, jint, jtext, jbool_or, jdoubles, jints, jarr, jcount

"""Число в стиле %.17g из C/C++: целые без дробной части, иначе shortest round-trip.

Julia печатает `15.0` для целых и `1.0e-12` для очень малых — первый случай
приводим к целому виду, второй уже валиден в JSON и понятен парсеру Python.
"""
function json_num(v::Real)
    (isnan(v) || isinf(v)) && return "0"
    v == 0 && return "0"
    if abs(v) < 1e15 && v == round(v)
        return string(round(Int64, v))
    end
    string(Float64(v))
end

function json_esc(s::AbstractString)
    io = IOBuffer()
    for c in s
        if c == '"'
            print(io, "\\\"")
        elseif c == '\\'
            print(io, "\\\\")
        elseif c == '\n'
            print(io, "\\n")
        elseif c == '\r'
            print(io, "\\r")
        elseif c == '\t'
            print(io, "\\t")
        else
            print(io, c)
        end
    end
    String(take!(io))
end

read_text(path::AbstractString) = read(path, String)
write_text(path::AbstractString, text::AbstractString) = write(path, text)

# ---------- доступ к разобранному ----------

jget(v::AbstractDict, key::AbstractString) =
    haskey(v, key) ? v[key] : error("JSON: нет ключа $key")

jdbl(v::AbstractDict, key::AbstractString) = Float64(jget(v, key))

function jdbl_or(v::AbstractDict, key::AbstractString, def::Real)
    haskey(v, key) && v[key] isa Real ? Float64(v[key]) : Float64(def)
end

jint(v::AbstractDict, key::AbstractString) = round(Int, jdbl(v, key))
jtext(v::AbstractDict, key::AbstractString) = String(jget(v, key))

function jbool_or(v::AbstractDict, key::AbstractString, def::Bool)
    haskey(v, key) && v[key] isa Bool ? v[key] : def
end

jdoubles(v::AbstractDict, key::AbstractString) =
    Float64[Float64(x) for x in jarr(jget(v, key))]

jints(v::AbstractDict, key::AbstractString) =
    Int[round(Int, Float64(x)) for x in jarr(jget(v, key))]

jarr(v) = v isa AbstractVector ? v : error("JSON: ожидался массив")
jcount(v) = length(jarr(v))

# ---------- разбор ----------

mutable struct Parser
    s::Vector{Char}
    i::Int
end

json_parse(text::AbstractString) = begin
    p = Parser(collect(text), 1)
    _skipws!(p)
    _value!(p)
end

function _skipws!(p::Parser)
    while p.i <= length(p.s) && isspace(p.s[p.i])
        p.i += 1
    end
end

function _value!(p::Parser)
    p.i > length(p.s) && error("JSON: неожиданный конец")
    c = p.s[p.i]
    if c == '{'
        return _object!(p)
    elseif c == '['
        return _array!(p)
    elseif c == '"'
        return _string!(p)
    elseif c == 't'
        _expect!(p, "true"); return true
    elseif c == 'f'
        _expect!(p, "false"); return false
    elseif c == 'n'
        _expect!(p, "null"); return nothing
    else
        return _number!(p)
    end
end

function _expect!(p::Parser, lit::String)
    for c in lit
        (p.i <= length(p.s) && p.s[p.i] == c) || error("JSON: ожидался литерал $lit")
        p.i += 1
    end
end

function _object!(p::Parser)
    d = Dict{String,Any}()
    p.i += 1                                  # {
    _skipws!(p)
    if p.s[p.i] == '}'
        p.i += 1
        return d
    end
    while true
        _skipws!(p)
        k = _string!(p)
        _skipws!(p)
        p.s[p.i] == ':' || error("JSON: ожидалось ':'")
        p.i += 1
        _skipws!(p)
        d[k] = _value!(p)
        _skipws!(p)
        c = p.s[p.i]
        p.i += 1
        c == '}' && return d
        c == ',' || error("JSON: ожидалась ',' или '}'")
    end
end

function _array!(p::Parser)
    a = Any[]
    p.i += 1                                  # [
    _skipws!(p)
    if p.s[p.i] == ']'
        p.i += 1
        return a
    end
    while true
        _skipws!(p)
        push!(a, _value!(p))
        _skipws!(p)
        c = p.s[p.i]
        p.i += 1
        c == ']' && return a
        c == ',' || error("JSON: ожидалась ',' или ']'")
    end
end

function _string!(p::Parser)
    p.s[p.i] == '"' || error("JSON: ожидалась строка")
    p.i += 1
    io = IOBuffer()
    while true
        c = p.s[p.i]
        p.i += 1
        if c == '"'
            return String(take!(io))
        elseif c != '\\'
            print(io, c)
            continue
        end
        e = p.s[p.i]
        p.i += 1
        if e == 'n'
            print(io, '\n')
        elseif e == 't'
            print(io, '\t')
        elseif e == 'r'
            print(io, '\r')
        elseif e == 'b'
            print(io, '\b')
        elseif e == 'f'
            print(io, '\f')
        elseif e == 'u'
            hex = String(p.s[p.i:(p.i + 3)])
            p.i += 4
            code = parse(UInt32, hex; base = 16)
            code < 0x80 ? print(io, Char(code)) : print(io, '?')
        else
            print(io, e)
        end
    end
end

function _number!(p::Parser)
    start = p.i
    while p.i <= length(p.s) && (p.s[p.i] in "+-0123456789.eE")
        p.i += 1
    end
    txt = String(p.s[start:(p.i - 1)])
    v = tryparse(Float64, txt)
    v === nothing && error("JSON: плохое число $txt")
    v
end

end # module Json
