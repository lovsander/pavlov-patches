package pappa

import (
	"path/filepath"
	"testing"
)

// TestConformanceVectors — проверка порта по «золотым» векторам из
// spec/conformance/vectors (те же файлы, что читает порт C++). Это и есть
// приёмка порта: go test ./...
func TestConformanceVectors(t *testing.T) {
	dir := filepath.Join("..", "..", "spec", "conformance", "vectors")
	results, err := CheckVectorsDir(dir)
	if err != nil {
		t.Fatalf("не удалось прочитать векторы (%s): %v", dir, err)
	}
	if len(results) == 0 {
		t.Fatalf("в %s нет векторов", dir)
	}
	for _, r := range results {
		if !r.OK {
			t.Errorf("вектор %s (%s, %s) не прошёл:\n  %s",
				r.File, r.Kind, r.Name, joinNotes(r.Notes))
		}
	}
	t.Logf("векторов проверено: %d", len(results))
}

func joinNotes(notes []string) string {
	out := ""
	for i, n := range notes {
		if i > 0 {
			out += "\n  "
		}
		out += n
	}
	return out
}
