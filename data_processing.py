from __future__ import annotations

import re
from typing import List, Tuple, Sequence, Union, Dict, Any

import numpy as np
from scipy.signal import savgol_filter, find_peaks
from scipy.sparse.linalg import spsolve
from scipy import sparse


ArrayLike = Union[np.ndarray, Sequence[float]]


def calculate_boxplot_stats(amplitudes_list: Sequence[Sequence[float]]) -> List[Dict[str, Any]]:
    """
    Рассчитывает статистики для box-plot по наборам амплитуд.
    :param amplitudes_list: последовательность массивов амплитуд
    :return: список словарей с q1, median, q3, нижней/верхней границей и выбросами
    """
    if not amplitudes_list:
        raise ValueError("amplitudes_list must contain at least one series")

    boxplot_stats: List[Dict[str, Any]] = []
    for amplitudes in amplitudes_list:
        array = np.asarray(amplitudes, dtype=float)
        if array.size == 0:
            continue

        q1 = np.percentile(array, 25)
        median = np.percentile(array, 50)
        q3 = np.percentile(array, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = array[(array < lower_bound) | (array > upper_bound)]

        boxplot_stats.append({
            'q1': float(q1),
            'median': float(median),
            'q3': float(q3),
            'lower_bound': float(lower_bound),
            'upper_bound': float(upper_bound),
            'outliers': outliers.tolist()
        })

    if not boxplot_stats:
        raise ValueError("No valid amplitude data for boxplot statistics")

    return boxplot_stats


def parse_txt_file(content: str) -> Tuple[List[float], List[float]]:
    """
    Парсит текстовый .txt с парами значений: частота амплитуда.
    Допускаются пробелы в качестве разделителей, запятая/точка как десятичный разделитель.
    """
    frequencies: List[float] = []
    amplitudes: List[float] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned = stripped.replace(',', '.')
        parts = cleaned.split()
        if len(parts) < 2:
            continue
        try:
            freq, ampl = map(float, parts[:2])
        except ValueError:
            continue
        frequencies.append(freq)
        amplitudes.append(ampl)

    if not frequencies:
        raise ValueError("Не найдено ни одной валидной пары в .txt файле")

    return frequencies, amplitudes


def parse_csv_file(content: str) -> Tuple[List[float], List[float]]:
    """
    Парсит .csv со строками "freq,ampl" или "freq;ampl". Десятичная запятая поддерживается.
    """
    frequencies: List[float] = []
    amplitudes: List[float] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        delimiter = ',' if ',' in stripped else (';' if ';' in stripped else None)
        if delimiter is None:
            continue
        parts = [part.replace(',', '.') for part in stripped.split(delimiter)]
        if len(parts) < 2:
            continue
        try:
            freq, ampl = map(float, parts[:2])
        except ValueError:
            continue
        frequencies.append(freq)
        amplitudes.append(ampl)

    if not frequencies:
        raise ValueError("Не найдено ни одной валидной пары в .csv файле")

    return frequencies, amplitudes


def parse_esp_file(file_content: str) -> Tuple[List[float], List[float]]:
    """
    Парсит .esp: строки из двух чисел (частота амплитуда) через пробел, строки с # игнорируются.
    :return: кортеж (frequencies, amplitudes)
    """
    frequencies: List[float] = []
    amplitudes: List[float] = []

    for line in file_content.splitlines():
        if line.startswith("#"):
            continue
        try:
            freq, ampl = map(float, line.split())
            frequencies.append(freq)
            amplitudes.append(ampl)
        except ValueError:
            continue

    return frequencies, amplitudes


def _parse_numeric_pairs_generic(content: str) -> Tuple[List[float], List[float]]:
    """Запасной парсер: находит первые два числа в строке (частота и амплитуда)."""
    frequencies: List[float] = []
    amplitudes: List[float] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        normalized = stripped.replace(',', '.')
        numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", normalized)
        if len(numbers) < 2:
            continue
        try:
            freq = float(numbers[0])
            ampl = float(numbers[1])
        except ValueError:
            continue
        frequencies.append(freq)
        amplitudes.append(ampl)

    if not frequencies:
        raise ValueError("Не найдено числовых пар (частота амплитуда) в содержимом")

    return frequencies, amplitudes


def parse_any_spectral_file(content: str) -> Tuple[List[float], List[float]]:
    parsers = (parse_csv_file, parse_txt_file, parse_esp_file)
    last_error: Exception | None = None

    for parser in parsers:
        try:
            frequencies, amplitudes = parser(content)
            if frequencies and amplitudes:
                return frequencies, amplitudes
        except ValueError as exc:
            last_error = exc

    try:
        return _parse_numeric_pairs_generic(content)
    except ValueError as exc:
        last_error = exc

    raise ValueError(str(last_error) if last_error else 'Не удалось распарсить спектральный файл')


def baseline_als(amplitudes: ArrayLike, lam: float, p: float, niter: int = 10) -> np.ndarray:
    """
    Оценка базовой линии методом ALS.
    - lam: параметр сглаживания (>0)
    - p: асимметрия (0 < p < 1)
    - niter: число итераций
    """
    if lam <= 0:
        raise ValueError("Параметр lam должен быть положительным")
    if not (0 < p < 1):
        raise ValueError("p должен быть в пределах (0, 1)")

    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if amplitudes.size == 0:
        raise ValueError("Массив амплитуд пуст")

    L = len(amplitudes)
    D = sparse.diags([1, -2, 1], [0, -1, -2], shape=(L, L - 2))
    w = np.ones(L)
    for _ in range(niter):
        W = sparse.spdiags(w, 0, L, L)
        Z = W + lam * D.dot(D.transpose())
        z = spsolve(Z, w * amplitudes)
        w = p * (amplitudes > z) + (1 - p) * (amplitudes < z)
    return z  # type: ignore[name-defined]


def smooth_signal(amplitudes: ArrayLike, window_length: int, polyorder: int) -> np.ndarray:
    """
    Сглаживание по Савицкому-Голею.
    - window_length: длина окна фильтра
    - polyorder: порядок полинома
    """
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if len(amplitudes) < window_length:
        raise ValueError("Длина сигнала меньше длины окна фильтра")
    if polyorder >= window_length:
        raise ValueError("Порядок полинома должен быть меньше длины окна")

    return savgol_filter(amplitudes, window_length, polyorder)


def normalize_snv(amplitudes: ArrayLike) -> np.ndarray:
    """Нормализация SNV (Standard Normal Variate)."""
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if amplitudes.size == 0:
        raise ValueError("Массив амплитуд пуст")

    mean = np.mean(amplitudes)
    std = np.std(amplitudes)
    if std == 0:
        raise ValueError("Стандартное отклонение равно нулю — нормализация невозможна")
    return (amplitudes - mean) / std


def find_signal_peaks(amplitudes: ArrayLike, width: float = 1, prominence: float = 1) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Поиск пиков в сигнале.
    - width: минимальная ширина пика
    - prominence: выраженность
    Возвращает индексы и словарь свойств.
    """
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if amplitudes.size == 0:
        return np.array([]), {}

    peaks, properties = find_peaks(amplitudes, width=width, prominence=prominence)
    return peaks, properties


def filter_frequency_range(
    frequencies: ArrayLike,
    amplitudes: ArrayLike,
    min_freq: float,
    max_freq: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Фильтрация диапазона частот [min_freq, max_freq].
    Возвращает отфильтрованные массивы той же длины.
    """
    if not isinstance(frequencies, np.ndarray):
        frequencies = np.array(frequencies)
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if frequencies.size == 0 or amplitudes.size == 0:
        raise ValueError("Пустые массивы частот или амплитуд")

    if min_freq > max_freq:
        raise ValueError("min_freq не может быть больше max_freq")

    mask = (frequencies >= min_freq) & (frequencies <= max_freq)

    if not np.any(mask):
        raise ValueError(f"Нет точек в диапазоне от {min_freq} до {max_freq}")

    filtered_frequencies = frequencies[mask]
    filtered_amplitudes = amplitudes[mask]

    return filtered_frequencies, filtered_amplitudes


def calculate_mean_std(amplitudes_list: Sequence[Sequence[float]]) -> Tuple[np.ndarray, np.ndarray]:
    """Среднее и стандартное отклонение по наборам амплитуд (по оси 0)."""
    amplitudes_array = np.array(amplitudes_list)
    mean_amplitude = np.mean(amplitudes_array, axis=0)
    std_amplitude = np.std(amplitudes_array, axis=0)

    return mean_amplitude, std_amplitude


def format_spectral_data(frequencies: Sequence[float], amplitudes: Sequence[float]) -> str:
    """Форматирует спектральные данные в табличный текст (freq\tampl)."""
    if len(frequencies) != len(amplitudes):
        raise ValueError("Длины массивов частот и амплитуд не совпадают")

    lines: List[str] = []
    for freq, ampl in zip(frequencies, amplitudes):
        lines.append(f"{freq:.2f}\t{ampl:.6f}")

    return "\n".join(lines)


def calculate_moving_average(amplitudes: ArrayLike, window_size: int) -> np.ndarray:
    """
    Скользящее среднее по окну указанной длины.
    :param amplitudes: массив амплитуд
    :param window_size: размер окна (целое > 0)
    :return: массив скользящего среднего
    """
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if amplitudes.size == 0:
        raise ValueError("Массив амплитуд пуст")

    if window_size <= 0:
        raise ValueError("Размер окна должен быть положительным")

    if window_size > len(amplitudes):
        raise ValueError("Размер окна не может превышать длину сигнала")

    moving_avg = np.convolve(amplitudes, np.ones(window_size) / window_size, mode='same')

    return moving_avg

