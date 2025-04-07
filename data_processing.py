import numpy as np
from scipy.signal import savgol_filter, find_peaks
from scipy.sparse.linalg import spsolve
from scipy import sparse
# усекии))
def calculate_boxplot_stats(amplitudes_list):
    """
    Вычисляет статистику для построения box plot (ящика с усами)
    :param amplitudes_list: список массивов амплитуд
    :return: список словарей с статистикой для каждого набора амплитуд
    """
    boxplot_stats = []
    for amplitudes in amplitudes_list:
        if len(amplitudes) == 0:
            continue
            
        q1 = np.percentile(amplitudes, 25)
        median = np.percentile(amplitudes, 50)
        q3 = np.percentile(amplitudes, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Находим выбросы
        outliers = amplitudes[(amplitudes < lower_bound) | (amplitudes > upper_bound)]
        
        boxplot_stats.append({
            'q1': q1,
            'median': median,
            'q3': q3,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'outliers': outliers.tolist() if len(outliers) > 0 else []
        })
    
    return boxplot_stats

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

    return filtered_frequencies, filtered_amplitudes

def calculate_mean_std(amplitudes_list):
    """
    Вычисляет среднее и стандартное отклонение для списка амплитуд.
    :param amplitudes_list: список массивов амплитуд
    :return: среднее и стандартное отклонение
    """
    amplitudes_array = np.array(amplitudes_list)
    mean_amplitude = np.mean(amplitudes_array, axis=0)
    std_amplitude = np.std(amplitudes_array, axis=0)

    return mean_amplitude, std_amplitude

def calculate_boxplot_stats(amplitudes_list):
    """
    Вычисляет статистику для построения box plot (ящика с усами)
    :param amplitudes_list: список массивов амплитуд
    :return: список словарей с статистикой для каждого набора амплитуд
    """
    import numpy as np
    
    boxplot_stats = []
    for amplitudes in amplitudes_list:
        if len(amplitudes) == 0:
            continue
            
        q1 = np.percentile(amplitudes, 25)
        median = np.percentile(amplitudes, 50)
        q3 = np.percentile(amplitudes, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Находим выбросы
        outliers = amplitudes[(amplitudes < lower_bound) | (amplitudes > upper_bound)]
        
        boxplot_stats.append({
            'q1': q1,
            'median': median,
            'q3': q3,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'outliers': outliers.tolist() if len(outliers) > 0 else []
        })
    
    return boxplot_stats

def format_spectral_data(frequencies, amplitudes):
    """Форматирует спектральные данные для сохранения"""
    if len(frequencies) != len(amplitudes):
        raise ValueError("Длины массивов частот и амплитуд не совпадают")
    
    lines = []
    for freq, ampl in zip(frequencies, amplitudes):
        lines.append(f"{freq:.2f}\t{ampl:.6f}")
    
    return "\n".join(lines)