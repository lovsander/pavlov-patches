// cmd/pappa — пайплайн PAPPA на Go: CSV с сечениями -> папка образца.
//
// Пишет ТОТ ЖЕ формат, что референс Python и порт C++ (CONTEXT §27):
//
//	<out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
//
// Проверка: python studies/verify_port.py --cpp-dir <out-dir>
//
// Запуск (пример):
//
//	go run ./cmd/pappa -input ../python/synthetic_data.csv -out-dir ../samples/body_go -name body
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"pavlov-patches/go/pappa"
)

func main() {
	input := flag.String("input", "", "CSV с колонками section_id,height_mm,angle_deg,radius_mm (обязательно)")
	outDir := flag.String("out-dir", "", "куда писать папку образца (обязательно)")
	name := flag.String("name", "sample", "имя образца (по умолчанию sample)")
	nPatches := flag.Int("n-patches", 7, "число патчей")
	phaseDeg := flag.Float64("phase-deg", 24.75, "общая фаза раскладки, °")
	degMin := flag.Int("deg-min", 4, "минимальная чётная степень")
	degMax := flag.Int("deg-max", 14, "максимальная чётная степень")
	overlapTrain := flag.Float64("overlap-train", 15.0, "перекрытие обучения, °")
	overlapUse := flag.Float64("overlap-use", 5.0, "перекрытие применения, °")
	elbowTol := flag.Float64("deg-elbow-tol", 0.05, "допуск правила «локтя»")
	degFloor := flag.Float64("deg-floor-mm", 0.0,
		"абсолютный пол RMSE, мм (0 = выключен): «идеально точно» -> степень не растёт")
	baselineDeg := flag.Float64("baseline-deg", 1.0, "окно снятия формы, °")
	iqrK := flag.Float64("iqr-k", 3.0, "множитель IQR (усы Тьюки)")
	pits := flag.Bool("pits", true, "фичер ям (по умолчанию включён, как в референсе)")
	quiet := flag.Bool("quiet", false, "только итог")
	flag.Parse()

	if *input == "" || *outDir == "" {
		flag.Usage()
		os.Exit(2)
	}

	rows, err := pappa.LoadCSV(*input)
	if err != nil {
		fail(err)
	}
	fmt.Printf("PAPPA (Go): %d точек, вход %s\n", len(rows), *input)

	opt := pappa.DefaultPipelineOptions()
	opt.Model.NPatches = *nPatches
	opt.Model.PhaseDeg = *phaseDeg
	opt.Model.DegMin = *degMin
	opt.Model.DegMax = *degMax
	opt.Model.OverlapTrain = *overlapTrain
	opt.Model.OverlapUse = *overlapUse
	opt.Model.DegElbowTol = *elbowTol
	opt.Model.DegFloorMM = *degFloor
	opt.Cleaner.BaselineDeg = *baselineDeg
	opt.Cleaner.IQRK = *iqrK
	opt.Pits = *pits
	opt.Verbose = !*quiet

	sections, err := pappa.ProcessSections(rows, opt)
	if err != nil {
		fail(err)
	}

	root, err := pappa.SaveSample(*outDir, *name, sections, pappa.SampleOptions{
		Name: *name, InputCSV: *input, Pits: opt.Pits,
		Description: fmt.Sprintf("собрано портом Go (PAPPA v%s)", pappa.PortVersion),
		Cleaner:     opt.Cleaner, Detector: opt.Detector,
	})
	if err != nil {
		fail(err)
	}

	fmt.Printf("\nОбразец записан: %s\n", root)
	fmt.Printf("  манифест: %s\n", filepath.Join(root, "sample.json"))
	fmt.Printf("  сечений:  %d (sections/*.pappa.json)\n", len(sections))
	fmt.Printf("\nСверка с референсом Python:\n")
	fmt.Printf("  python python/studies/verify_port.py --cpp-dir %s\n", root)
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, "Ошибка:", err)
	os.Exit(1)
}
