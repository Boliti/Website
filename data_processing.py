import numpy as np
from scipy.signal import savgol_filter, find_peaks
from scipy.sparse.linalg import spsolve
from scipy import sparse



def parse_esp_file(file_content):
    """
    Парсит данные из .esp файла.
    :param file_content: Содержимое файла в строковом формате
    :return: Кортеж (frequencies, amplitudes)
    """
    frequencies = []
    amplitudes = []

    for line in file_content.splitlines():
        # Пропускаем строки с метаданными
        if line.startswith("#"):
            continue

        # Разделяем строки на значения
        try:
            freq, ampl = map(float, line.split())
            frequencies.append(freq)
            amplitudes.append(ampl)
        except ValueError:
            # Игнорируем строки, которые не могут быть преобразованы
            continue

    return frequencies, amplitudes


def baseline_als(amplitudes, lam, p, niter=10):
    """
    Удаление базовой линии методом ALS.
    Параметры:
    - lam: параметр сглаживания (λ)
    - p: параметр весов (0 < p < 1)
    - niter: количество итераций
    """
    if lam <= 0:
        raise ValueError("λ должно быть положительным.")
    if not (0 < p < 1):
        raise ValueError("p должно быть между 0 и 1.")
    
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if amplitudes.size == 0:
        raise ValueError("Массив амплитуд пустой.")

    L = len(amplitudes)
    D = sparse.diags([1, -2, 1], [0, -1, -2], shape=(L, L - 2))
    w = np.ones(L)
    for i in range(niter):
        W = sparse.spdiags(w, 0, L, L)
        Z = W + lam * D.dot(D.transpose())
        z = spsolve(Z, w * amplitudes)
        w = p * (amplitudes > z) + (1 - p) * (amplitudes < z)
    return z

def smooth_signal(amplitudes, window_length, polyorder):
    """
    Сглаживание сигнала методом Савицкого-Голая.
    Параметры:
    - window_length: длина окна сглаживания
    - polyorder: порядок полинома
    """
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if len(amplitudes) < window_length:
        raise ValueError("Длина сигнала меньше размера окна сглаживания.")
    if polyorder >= window_length:
        raise ValueError("Порядок полинома должен быть меньше длины окна.")
    
    return savgol_filter(amplitudes, window_length, polyorder)

def normalize_snv(amplitudes):
    """
    Нормализация методом SNV (Standard Normal Variate).
    """
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if amplitudes.size == 0:
        raise ValueError("Массив амплитуд пустой.")

    mean = np.mean(amplitudes)
    std = np.std(amplitudes)
    if std == 0:
        raise ValueError("Стандартное отклонение равно нулю. Нормализация невозможна.")
    return (amplitudes - mean) / std

def find_signal_peaks(amplitudes, width=1, prominence=1):
    """
    Поиск пиков в массиве амплитуд.
    Параметры:
    - amplitudes: массив амплитуд
    - width: ширина пиков
    - prominence: значимость пиков
    Возвращает:
    - indices: индексы пиков
    - properties: свойства пиков
    """
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if amplitudes.size == 0:
        return [], {}

    peaks, properties = find_peaks(amplitudes, width=width, prominence=prominence)
    return peaks, properties

def filter_frequency_range(frequencies, amplitudes, min_freq, max_freq):
    """
    Фильтрация данных по заданному диапазону частот.
    Параметры:
    - frequencies: массив частот
    - amplitudes: массив амплитуд
    - min_freq: минимальная частота
    - max_freq: максимальная частота
    """
    if not isinstance(frequencies, np.ndarray):
        frequencies = np.array(frequencies)
    if not isinstance(amplitudes, np.ndarray):
        amplitudes = np.array(amplitudes)

    if frequencies.size == 0 or amplitudes.size == 0:
        raise ValueError("Один из массивов (частоты или амплитуды) пустой.")

    if min_freq > max_freq:
        raise ValueError("Минимальная частота должна быть меньше или равна максимальной частоте.")

    # Применение маски
    mask = (frequencies >= min_freq) & (frequencies <= max_freq)

    if not np.any(mask):
        raise ValueError(f"Нет данных в диапазоне частот от {min_freq} до {max_freq}.")

    filtered_frequencies = frequencies[mask]
    filtered_amplitudes = amplitudes[mask]

    print(f"Фильтрованные частоты (первые 10): {filtered_frequencies[:10]}")
    print(f"Начальная частота: {filtered_frequencies[0]}")
    return filtered_frequencies, filtered_amplitudes


