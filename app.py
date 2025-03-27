import os
from flask import Flask, request, jsonify, render_template
import numpy as np
from data_processing import (
    baseline_als,
    smooth_signal,
    normalize_snv,
    find_signal_peaks,
    filter_frequency_range,
    parse_esp_file,
    calculate_mean_std, 
    calculate_boxplot_stats
)

# Инициализация Flask приложения
app = Flask(__name__)

# Директория для загрузки файлов
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    """
    Отображение главной страницы.
    """
    return render_template('index.html')

@app.route('/upload_files', methods=['POST'])
def upload_files():
    """
    Загрузка файлов и извлечение данных частот и амплитуд.
    """
    if 'files' not in request.files:
        return jsonify({'error': 'Файлы не найдены'}), 400

    files = request.files.getlist('files')
    all_frequencies = []
    all_amplitudes = []
    file_names = []

    try:
        for file in files:
            if file.filename == '':
                return jsonify({'error': 'Один из файлов не имеет имени'}), 400

            filename = file.filename.lower()
            content = file.read().decode('utf-8')

            frequencies = []
            amplitudes = []

            if filename.endswith('.esp'):
                # Обработка файлов .esp
                try:
                    frequencies, amplitudes = parse_esp_file(content)
                except Exception as e:
                    return jsonify({'error': f'Ошибка при обработке файла {file.filename}: {str(e)}'}), 400
            elif filename.endswith('.txt') or filename.endswith('.csv'):
                # Обработка файлов .txt/.csv
                try:
                    lines = content.splitlines()
                    for line in lines:
                        if line.startswith("#"):
                            continue
                        if ',' in line:
                            parts = line.split(',')
                        elif ';' in line:
                            parts = line.split(';')
                        else:
                            parts = line.split()  # На случай разделения пробелами
                        if len(parts) == 2:
                            freq, ampl = map(float, parts)
                            frequencies.append(freq)
                            amplitudes.append(ampl)
                        else:
                            return jsonify({'error': f'Неверный формат данных в файле {file.filename}'}), 400
                except Exception as e:
                    return jsonify({'error': f'Ошибка при чтении файла {file.filename}: {str(e)}'}), 400
            else:
                return jsonify({'error': f'Неподдерживаемый тип файла: {file.filename}'}), 400

            # Сохраняем результаты
            all_frequencies.append(frequencies)
            all_amplitudes.append(amplitudes)
            file_names.append(file.filename)

        return jsonify({
            'message': 'Файлы успешно загружены!',
            'files': file_names,
            'frequencies': all_frequencies,
            'amplitudes': all_amplitudes
        })

    except Exception as e:
        return jsonify({'error': f'Ошибка обработки файлов: {str(e)}'}), 400


@app.route('/process_data', methods=['POST'])
def process_data():
    try:
        # Получаем данные из запроса
        data = request.json
        frequencies_list = data['frequencies']
        amplitudes_list = data['amplitudes']
        min_freq = data.get('min_freq', 0)
        max_freq = data.get('max_freq', 10000)
        remove_baseline = data.get('remove_baseline', False)
        apply_smoothing = data.get('apply_smoothing', False)
        normalize = data.get('normalize', False)
        find_peaks_flag = data.get('find_peaks', False)
        calculate_boxplot_flag = data.get('calculate_boxplot', False)
        calculate_mean_std_flag = data.get('calculate_mean_std', False)
        width = data.get('width', 1)
        prominence = data.get('prominence', 1)
        

        # Обработка данных
        allFrequencies = []
        allAmplitudes = []
        peaks_list = []
        peaks_values_list = []

        for frequencies, amplitudes in zip(frequencies_list, amplitudes_list):
            # Фильтрация по частотам
            frequencies, amplitudes = filter_frequency_range(frequencies, amplitudes, min_freq, max_freq)

            # Удаление базовой линии
            if remove_baseline:
                amplitudes -= baseline_als(amplitudes, data.get('lam', 1000), data.get('p', 0.001))

            # Сглаживание
            if apply_smoothing:
                amplitudes = smooth_signal(amplitudes, data.get('window_length', 25), data.get('polyorder', 2))

            # Нормализация
            if normalize:
                amplitudes = normalize_snv(amplitudes)

            # Поиск пиков
            peaks = []
            peaks_values = []
            if find_peaks_flag:
                peaks, _ = find_signal_peaks(amplitudes, width=width, prominence=prominence)
                peaks_values = amplitudes[peaks] if len(peaks) > 0 else []

            boxplot_stats = []
            if data.get('calculate_boxplot', False) and len(allAmplitudes) > 0:
                boxplot_stats = calculate_boxplot_stats(allAmplitudes)


            # Сохраняем результаты
            allFrequencies.append(frequencies)
            allAmplitudes.append(amplitudes)
            peaks_list.append(peaks.tolist() if len(peaks) > 0 else [])
            peaks_values_list.append(peaks_values.tolist() if len(peaks_values) > 0 else [])

        mean_amplitude, std_amplitude = [], []
        if calculate_mean_std_flag and len(allAmplitudes) > 0:
            mean_amplitude, std_amplitude = calculate_mean_std(allAmplitudes)
        

        return jsonify({
            'frequencies': [f.tolist() for f in allFrequencies],
            'processed_amplitudes': [a.tolist() for a in allAmplitudes],
            'peaks': peaks_list,
            'peaks_values': peaks_values_list,
            'mean_amplitude': mean_amplitude.tolist() if len(mean_amplitude) > 0 else [],
            'boxplot_stats': boxplot_stats,
            'std_amplitude': std_amplitude.tolist() if len(std_amplitude) > 0 else []
            
        })

    except Exception as e:
        print(f"Ошибка обработки данных: {str(e)}")
        return jsonify({'error': f"Ошибка обработки данных: {str(e)}"}), 400


@app.route('/export_mean_spectrum', methods=['POST'])
def export_mean_spectrum():
    try:
        data = request.json
        frequencies = np.array(data['frequencies'])
        mean_amplitude = np.array(data['mean_amplitude'])
        params = data.get('params', {})

        # Создаем CSV-строку с метаданными
        metadata_lines = ["# Metadata"]
        for param, value in params.items():
            metadata_lines.append(f"# {param}: {value}")
        metadata_str = "; ".join(metadata_lines)

        csv_data = f"{metadata_str}\n#frequency,mean_amplitude\n"
        csv_data += "\n".join([f"{freq},{amp}" for freq, amp in zip(frequencies, mean_amplitude)])

        response = app.response_class(
            csv_data,
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=mean_spectrum.csv'
            }
        )
        return response

    except Exception as e:
        return jsonify({'error': str(e)}), 400



if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")

