// cmd/conformance — проверка Go-порта по конформанс-векторам.
//
// Те же файлы, что читает порт C++ (spec/conformance/vectors), поэтому
// «правильность» порта не зависит от языка референса. Коды: 0 — всё сошлось,
// 1 — расхождения, 2 — нет каталога.
//
// Запуск:  go run ./cmd/conformance ../../spec/conformance/vectors
//
//	либо: go test ./...   (то же самое, но через тест Go)
package main

import (
	"fmt"
	"os"

	"pavlov-patches/go/pappa"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Использование: conformance <каталог с векторами>")
		fmt.Println("  например:  go run ./cmd/conformance ../spec/conformance/vectors")
		os.Exit(2)
	}
	dir := os.Args[1]
	results, err := pappa.CheckVectorsDir(dir)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Ошибка:", err)
		os.Exit(2)
	}

	fmt.Printf("Конформанс-векторы PAPPA (Go): %d файл(ов) в %s\n\n", len(results), dir)
	failed := 0
	for _, r := range results {
		mark := "[OK]   "
		if !r.OK {
			mark = "[FAIL] "
			failed++
		}
		fmt.Printf("%s%s  (%s, %s)\n", mark, r.File, r.Kind, r.Name)
		for _, note := range r.Notes {
			fmt.Printf("         %s\n", note)
		}
	}
	fmt.Printf("\nИтог: %d/%d векторов пройдено\n", len(results)-failed, len(results))
	if failed > 0 {
		os.Exit(1)
	}
}
