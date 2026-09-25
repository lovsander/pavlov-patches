// Отладочная утилита (не входит в сборку пайплайна, см. cpp/CMakeLists.txt).
// Собрана под старый набор файлов; актуальная точка входа — main.cpp.

#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <cmath>
#include <string>
#include <algorithm>

int main() {
    std::ifstream file("synthetic_data.csv");
    if (!file.is_open()) {
        std::cerr << "НЕ ОТКРЫЛСЯ\n";
        return 1;
    }

    std::string line;
    std::getline(file, line); // header
    std::cout << "HEADER: " << line << "\n\n";

    for (int i = 0; i < 5; ++i) {
        if (!std::getline(file, line)) break;
        line.erase(std::remove(line.begin(), line.end(), '\r'), line.end());

        std::cout << "=== Строка " << i+1 << " ===\n";
        std::cout << "RAW: [" << line << "]\n";

        std::stringstream ss(line);
        std::string token;
        int k = 0;
        while (std::getline(ss, token, ',')) {
            std::cout << "  [" << k++ << "] = " << token << "\n";
        }
        std::cout << "\n";
    }
    return 0;
}