import os
from flask import Flask, request, jsonify, render_template, send_file
import numpy as np
from data_processing import (
    baseline_als,
    smooth_signal,
    normalize_snv,
    find_signal_peaks,
    filter_frequency_range,
    parse_esp_file,
    calculate_mean_std, 
    calculate_boxplot_stats,
    parse_txt_file,
    parse_csv_file
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
            elif filename.endswith('.txt'):
                frequencies, amplitudes = parse_txt_file(content)
            elif filename.endswith('.csv'):
                frequencies, amplitudes = parse_csv_file(content)
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

import zipfile
import io
from datetime import datetime

@app.route('/export_processed_data', methods=['POST'])
def export_processed_data():
    try:
        data = request.json
        frequencies = data['frequencies']
        amplitudes = data['amplitudes']  # Это уже обработанные амплитуды
        file_names = data['fileNames']
        params = data['params']

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for i, (freq, ampl, name) in enumerate(zip(frequencies, amplitudes, file_names)):
                base_name = f"spectrum_{i+1}" if not name else name.split('.')[0]
                file_name = f"{base_name}_processed.txt"
                
                content = "# Processed spectral data (after transformations)\n"
                content += f"# Original file: {name}\n"
                content += "# Processing parameters:\n"
                for param, value in params.items():
                    content += f"# {param}: {value}\n"
                content += "# Wavenumber (cm⁻¹)\tIntensity (a.u.)\n"
                
                for wavenumber, intensity in zip(freq, ampl):
                    content += f"{wavenumber}\t{intensity}\n"
                
                zip_file.writestr(file_name, content)
            
            # Файл с метаданными
            meta_content = "# Processing metadata\n"
            meta_content += f"# Export date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            meta_content += "# Applied transformations:\n"
            if params.get('remove_baseline'):
                meta_content += "# - Baseline removal applied\n"
            if params.get('apply_smoothing'):
                meta_content += "# - Smoothing applied\n"
            if params.get('normalize'):
                meta_content += "# - Normalization applied\n"
            meta_content += "# Parameters:\n"
            for param, value in params.items():
                meta_content += f"# {param}: {value}\n"
            
            zip_file.writestr("processing_metadata.txt", meta_content)

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='processed_spectra.zip'
        )

    except Exception as e:
        print(f"Ошибка экспорта: {str(e)}")
        return jsonify({'error': f"Ошибка экспорта: {str(e)}"}), 500

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

