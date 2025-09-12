let allFrequencies = [];
let allAmplitudes = [];
let fileNames = [];
let processedData = {
    frequencies: [],
    amplitudes: [],
    fileNames: [],
    params: {}
};
let latestMeanAmplitude = [];


function plotCombinedSpectrum(allFrequencies, allAmplitudes, fileNames, allPeaks, mean_amplitude, std_amplitude, showOnlyMeanStd, boxplotStats, title) {
    const plotData = [];
    const lineColors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b'];

    // Линейные графики для каждого файла
    if (!showOnlyMeanStd) {
        for (let i = 0; i < allFrequencies.length; i++) {
            plotData.push({
                x: allFrequencies[i],
                y: allAmplitudes[i],
                type: 'scatter',
                mode: 'lines',
                name: truncateFileName(fileNames[i]) || `Файл ${i + 1}`,
                line: { 
                    color: lineColors[i % lineColors.length],
                    width: 1
                },
                yaxis: 'y1'
            });
        
            if (allPeaks[i] && allPeaks[i].length > 0) {
                // Точки пиков
                const peakX = allPeaks[i].map(index => allFrequencies[i][index]);
                const peakY = allPeaks[i].map(index => allAmplitudes[i][index]);

                plotData.push({
                    x: peakX,
                    y: peakY,
                    type: 'scatter',
                    mode: 'markers+text',
                    name: `Пики ${truncateFileName(fileNames[i]) || `Файл ${i + 1}`}`,
                    marker: { color: lineColors[i % lineColors.length], size: 8, symbol: 'circle-open' },
                    text: peakX.map(coord => coord.toFixed(2)),
                    textposition: 'top center',
                    textfont: {
                        size: 10,
                        color: lineColors[i % lineColors.length]
                    },
                    yaxis: 'y1'
                });
            }
        }
    }

    // Среднее значение и стандартное отклонение
    if (mean_amplitude && mean_amplitude.length > 0 && std_amplitude && std_amplitude.length > 0) {
        plotData.push(
            {
                x: allFrequencies[0],
                y: mean_amplitude,
                type: 'scatter',
                mode: 'lines',
                name: 'Среднее значение',
                line: { color: 'red', width: 3 },
                yaxis: 'y1'
            },
            {
                x: allFrequencies[0],
                y: mean_amplitude.map((m, i) => m + std_amplitude[i]),
                type: 'scatter',
                mode: 'lines',
                name: 'Среднее + 1σ',
                line: { color: 'orange', width: 2, dash: 'dot' },
                yaxis: 'y1'
            },
            {
                x: allFrequencies[0],
                y: mean_amplitude.map((m, i) => m - std_amplitude[i]),
                type: 'scatter',
                mode: 'lines',
                name: 'Среднее - 1σ',
                line: { color: 'orange', width: 2, dash: 'dot' },
                yaxis: 'y1'
            }
        );
    }

    // Box plots
    if (boxplotStats && boxplotStats.length > 0) {
        const positions = [];
        const step = (allFrequencies[0][allFrequencies[0].length - 1] - allFrequencies[0][0]) / (allFrequencies.length + 1);

        for (let i = 0; i < allFrequencies.length; i++) {
            positions.push(allFrequencies[0][0] + (i + 1) * step);
        }

        plotData.push({
            y: allAmplitudes.flat(),
            x: positions.flatMap((pos, i) => Array(allAmplitudes[i].length).fill(pos)),
            type: 'box',
            name: 'Распределение',
            boxpoints: 'all',
            jitter: 0.5,
            pointpos: 0,
            marker: { size: 3, opacity: 0.5 },
            line: { width: 1 },
            fillcolor: 'rgba(100, 100, 255, 0.3)',
            yaxis: 'y1',
            hoverinfo: 'y+name',
            showlegend: false
        });
    }

    const layout = {
        title: title,
        xaxis: { title: 'Волновое число (см⁻¹)' },
        yaxis: { title: 'Интенсивность (Отн. ед.)' },
        plot_bgcolor: document.body.classList.contains('dark-theme') ? '#1e1e1e' : '#ffffff',
        paper_bgcolor: document.body.classList.contains('dark-theme') ? '#1e1e1e' : '#ffffff',
        font: { color: document.body.classList.contains('dark-theme') ? '#e0e0e0' : '#222' },
        showlegend: true,
        legend: {
            orientation: 'v',
            y: 1,
            x: 1.02,
            yanchor: 'top',
            xanchor: 'left'
        },
        margin: { l: 60, r: 150, b: 60, t: 80, pad: 4 }
    };

    Plotly.newPlot('spectrum_plot', plotData, layout);
}

function truncateFileName(name, length = 20) {
    return name.length > length ? name.slice(0, length - 3) + '...' : name;
}



async function uploadFiles() {
    const files = document.getElementById('files').files;
    if (files.length === 0) {
        alert('Пожалуйста, выберите файлы для загрузки');
        return;
    }

    const formData = new FormData();
    for (let file of files) {
        formData.append('files', file);
    }

    try {
        const response = await fetch('/upload_files', {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();

        if (result.frequencies && result.amplitudes) {
            allFrequencies = result.frequencies.map(arr => arr.map(Number));
            allAmplitudes = result.amplitudes.map(arr => arr.map(Number));
            fileNames = result.files;

            plotCombinedSpectrum(
                allFrequencies, 
                allAmplitudes, 
                fileNames, 
                new Array(allFrequencies.length).fill([]),
                [], // mean_amplitude
                [], // std_amplitude
                false, 
                [], // boxplotStats
                "Исходные спектры"
            );

            alert(`Успешно загружено ${result.files.length} файлов`);
        } else {
            throw new Error(result.error || 'Неизвестная ошибка при загрузке');
        }
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        alert('Ошибка: ' + error.message);
    }
}

async function processAndPlot() {
    console.log("Обработка данных...");

    if (allFrequencies.length === 0 || allAmplitudes.length === 0) {
        alert("Данные не загружены. Сначала загрузите файлы.");
        return;
    }

    try {
        const getNumberValue = (id, defaultValue) => {
            const val = document.getElementById(id).value;
            return val === '' ? defaultValue : Number(val);
        };

        const params = {
            frequencies: allFrequencies,
            amplitudes: allAmplitudes,
            remove_baseline: document.getElementById('remove_baseline').checked,
            apply_smoothing: document.getElementById('apply_smoothing').checked,
            normalize: document.getElementById('normalize').checked,
            find_peaks: document.getElementById('find_peaks').checked,
            calculate_mean_std: document.getElementById('calculate_mean_std').checked,
            calculate_boxplot: document.getElementById('calculate_boxplot').checked,
            lam: getNumberValue('lam', 1000),
            p: getNumberValue('p', 0.001),
            window_length: getNumberValue('window_length', 25),
            polyorder: getNumberValue('polyorder', 2),
            width: getNumberValue('peak_width', 1),
            prominence: getNumberValue('peak_prominence', 1),
            min_freq: getNumberValue('min_freq', 0),
            max_freq: getNumberValue('max_freq', 10000),
        };

        const response = await fetch('/process_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Ошибка сервера: ${response.status} ${errorText}`);
        }

        const result = await response.json();

        // Сохраняем обработанные данные для экспорта
        processedData = {
            frequencies: result.frequencies,
            amplitudes: result.processed_amplitudes,
            fileNames: fileNames,
            params: params
        };

        plotCombinedSpectrum(
            result.frequencies,
            result.processed_amplitudes,
            fileNames,
            result.peaks || [],
            result.mean_amplitude || [],
            result.std_amplitude || [],
            document.getElementById('show_only_mean_std').checked,
            result.boxplot_stats || [],
            "Обработанные спектры"
        );
        
        window.latestMeanAmplitude = result.mean_amplitude;

        if (document.getElementById('show_peak_table').checked && result.peaks && result.peaks.length > 0) {
            renderPeakTable(result.frequencies, result.processed_amplitudes, result.peaks, fileNames);
        } else {
            document.getElementById('peak_table_container').innerHTML = '';
        }

    } catch (error) {
        console.error("Ошибка:", error);
        alert("Ошибка обработки: " + error.message);
    }
}

async function downloadProcessedData() {
    if (processedData.frequencies.length === 0) {
        alert("Нет обработанных данных для сохранения. Сначала обработайте файлы.");
        return;
    }

    try {
        const response = await fetch('/export_processed_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(processedData),
        });

        if (!response.ok) throw new Error('Ошибка экспорта');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'processed_spectra.zip';
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch (error) {
        console.error("Ошибка экспорта:", error);
        alert("Ошибка экспорта: " + error.message);
    }
}

async function downloadMeanSpectrum() {
    if (!allFrequencies.length || !window.latestMeanAmplitude) {
        alert("Сначала загрузите и обработайте данные.");
        return;
    }

    const params = {
        remove_baseline: document.getElementById('remove_baseline').checked,
        lam: document.getElementById('lam').value || "1000",
        p: document.getElementById('p').value || "0.001",
        apply_smoothing: document.getElementById('apply_smoothing').checked,
        window_length: document.getElementById('window_length').value || "25",
        polyorder: document.getElementById('polyorder').value || "1",
        normalize: document.getElementById('normalize').checked,
        find_peaks: document.getElementById('find_peaks').checked,
        peak_width: document.getElementById('peak_width').value || "1",
        peak_prominence: document.getElementById('peak_prominence').value || "1",
        calculate_mean_std: document.getElementById('calculate_mean_std').checked,
        calculate_boxplot: document.getElementById('calculate_boxplot').checked,
        min_freq: document.getElementById('min_freq').value || "0",
        max_freq: document.getElementById('max_freq').value || "10000"
    };

    try {
        const exportParams = {
            frequencies: allFrequencies[0],
            mean_amplitude: window.latestMeanAmplitude,
            params: params
        };

        const response = await fetch('/export_mean_spectrum', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(exportParams),
        });

        if (!response.ok) throw new Error('Ошибка экспорта');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'mean_spectrum.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();

    } catch (error) {
        console.error("Ошибка экспорта:", error);
        alert("Ошибка экспорта: " + error.message);
    }
}



function renderPeakTable(frequenciesList, amplitudesList, peaksList, fileNames) {
    const container = document.getElementById('peak_table_container');
    container.innerHTML = ''; // Очищаем перед отрисовкой

    peaksList.forEach((peaks, index) => {
        if (!peaks || peaks.length === 0) return;

        const table = document.createElement('table');
        table.style.borderCollapse = 'collapse';
        table.style.marginBottom = '20px';
        table.style.width = '100%';

        const caption = document.createElement('caption');
        caption.textContent = `Пики — ${fileNames[index] || `Файл ${index + 1}`}`;
        caption.style.fontWeight = 'bold';
        table.appendChild(caption);

        const headerRow = document.createElement('tr');
        ['#', 'Частота (см⁻¹)', 'Интенсивность'].forEach(text => {
            const th = document.createElement('th');
            th.textContent = text;
            th.style.border = '1px solid #ccc';
            th.style.padding = '5px';
            th.style.backgroundColor = '#f0f0f0';
            headerRow.appendChild(th);
        });
        table.appendChild(headerRow);

        peaks.forEach((peakIdx, i) => {
            const row = document.createElement('tr');

            const freq = frequenciesList[index][peakIdx];
            const amp = amplitudesList[index][peakIdx];

            [i + 1, freq.toFixed(2), amp.toFixed(2)].forEach(val => {
                const td = document.createElement('td');
                td.textContent = val;
                td.style.border = '1px solid #ccc';
                td.style.padding = '5px';
                row.appendChild(td);
            });

            table.appendChild(row);
        });

        container.appendChild(table);
    });
}
// Остальные функции (plotCombinedSpectrum, renderPeakTable, updatePlotTheme, truncateFileName) остаются без изменений

document.addEventListener('DOMContentLoaded', function() {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            document.body.classList.toggle('dark-theme');
            updatePlotTheme();
        });
    }
});