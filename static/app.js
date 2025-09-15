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
console.log('app.js loaded successfully');

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded');
    console.log('Files input:', document.getElementById('files'));
    console.log('Plot element:', document.getElementById('spectrum_plot'));
});

function truncateFileName(name, length = 20) {
    if (!name) return `Файл`;
    return name.length > length ? name.slice(0, length - 3) + '...' : name;
}

function plotCombinedSpectrum(allFrequencies, allAmplitudes, fileNames, allPeaks, mean_amplitude, std_amplitude, showOnlyMeanStd, boxplotStats, title, movingAverages = []) {
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

            // Скользящая средняя (если есть)
            if (movingAverages && movingAverages[i] && movingAverages[i].length > 0) {
                plotData.push({
                    x: allFrequencies[i],
                    y: movingAverages[i],
                    type: 'scatter',
                    mode: 'lines',
                    name: `Ср. ${truncateFileName(fileNames[i])}`,
                    line: { 
                        color: lineColors[i % lineColors.length],
                        width: 2,
                        dash: 'dash'
                    },
                    opacity: 0.8,
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
                y: mean_amplitude.map((m, idx) => m + std_amplitude[idx]),
                type: 'scatter',
                mode: 'lines',
                name: 'Среднее + 1σ',
                line: { color: 'orange', width: 2, dash: 'dot' },
                yaxis: 'y1'
            },
            {
                x: allFrequencies[0],
                y: mean_amplitude.map((m, idx) => m - std_amplitude[idx]),
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

        for (let idx = 0; idx < allFrequencies.length; idx++) {
            positions.push(allFrequencies[0][0] + (idx + 1) * step);
        }

        plotData.push({
            y: allAmplitudes.flat(),
            x: positions.flatMap((pos, idx) => Array(allAmplitudes[idx].length).fill(pos)),
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
        title: title.includes('(') ? title : title + ` (${allFrequencies.length} файлов)`,
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

    Plotly.newPlot('spectrum_plot', plotData, layout).then(function() {
        initLegendHover();
    });
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

        if (!response.ok) {
            throw new Error(`Ошибка сервера: ${response.status}`);
        }

        const result = await response.json();

        if (result.frequencies && result.amplitudes) {
            // Заменяем данные полностью (а не добавляем)
            allFrequencies = result.frequencies.map(arr => arr.map(Number));
            allAmplitudes = result.amplitudes.map(arr => arr.map(Number));
            fileNames = result.files;

            if (document.getElementById('spectrum_plot')) {
                plotCombinedSpectrum(
                    allFrequencies, 
                    allAmplitudes, 
                    fileNames, 
                    new Array(allFrequencies.length).fill([]),
                    [], // mean_amplitude
                    [], // std_amplitude
                    false, 
                    [], // boxplotStats
                    "Исходные спектры (" + allFrequencies.length + " файлов)"
                );
            }

            alert(`Загружено ${result.files.length} файлов`);
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
            show_moving_average: document.getElementById('show_moving_average').checked,
            moving_average_window: getNumberValue('moving_average_window', 10)
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

        processedData = {
            frequencies: result.frequencies,
            amplitudes: result.processed_amplitudes,
            fileNames: fileNames, // Используем текущие fileNames
            params: params
        };

        plotCombinedSpectrum(
            result.frequencies,
            result.processed_amplitudes,
            fileNames, // Используем текущие fileNames
            result.peaks || [],
            result.mean_amplitude || [],
            result.std_amplitude || [],
            document.getElementById('show_only_mean_std').checked,
            result.boxplot_stats || [],
            "Обработанные спектры (" + result.frequencies.length + " файлов)",
            result.moving_averages || []
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
    container.innerHTML = '';

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

        peaks.forEach((peakIdx, peakIndex) => {
            const row = document.createElement('tr');

            const freq = frequenciesList[index][peakIdx];
            const amp = amplitudesList[index][peakIdx];

            [peakIndex + 1, freq.toFixed(2), amp.toFixed(2)].forEach(val => {
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



function highlightSingleSpectrum(curveNumber) {
    // Получаем информацию о всех кривых
    Plotly.restyle('spectrum_plot', {
        'line.width': Array(100).fill(1) // Сначала сбрасываем все
    }).then(function() {
        // Затем выделяем только одну нужную кривую
        Plotly.restyle('spectrum_plot', {
            'line.width': 4
        }, [curveNumber]);
    });
}

function resetSpectrumHighlight() {
    // Получаем текущее состояние всех кривых
    Plotly.update('spectrum_plot', {
        'line.width': 1
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            document.body.classList.toggle('dark-theme');
        });
    }
});

// Добавьте эту функцию в app.js
function initTooltips() {
    const helpIcons = document.querySelectorAll('.help-icon');
    
    helpIcons.forEach(icon => {
        // Следим за движением мыши над иконкой
        icon.addEventListener('mousemove', function(e) {
            const tooltip = this.querySelector('::after') || this;
            const tooltipText = this.getAttribute('data-tooltip');
            
            if (tooltipText) {
                // Позиционируем подсказку рядом с курсором
                const x = e.clientX + 15;
                const y = e.clientY + 15;
                
                // Создаем или обновляем стиль подсказки
                let style = document.getElementById('tooltip-style');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'tooltip-style';
                    document.head.appendChild(style);
                }
                
                style.textContent = `
                    .help-icon:hover::after {
                        left: ${x}px !important;
                        top: ${y}px !important;
                        transform: none !important;
                    }
                `;
            }
        });
        
        // При уходе с иконки убираем подсказку
        icon.addEventListener('mouseleave', function() {
            const style = document.getElementById('tooltip-style');
            if (style) {
                style.remove();
            }
        });
    });
}


document.addEventListener('DOMContentLoaded', function() {
    initTooltips();
});



// Добавьте эту функцию для обработки кликов по линиям графика
function initGraphClickHandler() {
    const plotElement = document.getElementById('spectrum_plot');
    
    plotElement.on('plotly_click', function(data) {
        if (data.points && data.points[0]) {
            const point = data.points[0];
            const traceName = point.data.name || '';
            
            // Игнорируем неспектральные элементы
            if (traceName.includes('Пики') || 
                traceName.includes('Среднее') ||
                traceName.includes('СКО') ||
                traceName.includes('Ср.') ||
                traceName.includes('+') ||
                traceName.includes('-')) {
                return;
            }
            
            // Находим индекс спектра
            const spectrumIndex = findSpectrumIndexByName(traceName);
            if (spectrumIndex !== -1) {
                showDeleteButton(data.event.clientX, data.event.clientY, spectrumIndex);
            }
        }
    });
}


// Добавьте переменную для хранения выбранного спектра
let selectedSpectrumIndex = -1;


function createDeleteButton() {
    if (!document.getElementById('delete-spectrum-btn')) {
        const deleteBtn = document.createElement('button');
        deleteBtn.id = 'delete-spectrum-btn';
        deleteBtn.className = 'delete-spectrum-btn';
        deleteBtn.textContent = 'Удалить';
        deleteBtn.onclick = removeSelectedSpectrum;
        document.body.appendChild(deleteBtn);
    }
    return document.getElementById('delete-spectrum-btn');
}

// Добавьте функцию для показа кнопки удаления
function showDeleteButton(x, y, spectrumIndex) {
    const deleteBtn = createDeleteButton();
    selectedSpectrumIndex = spectrumIndex;
    
    deleteBtn.style.left = (x + 10) + 'px';
    deleteBtn.style.top = (y + 10) + 'px';
    deleteBtn.style.display = 'block';
    
    // Скрываем кнопку через 3 секунды или при клике вне её
    setTimeout(() => {
        if (deleteBtn.style.display === 'block') {
            deleteBtn.style.display = 'none';
        }
    }, 3000);
}

// Функция удаления спектра
function removeSelectedSpectrum() {
    if (selectedSpectrumIndex === -1) return;
    
    // Скрываем кнопку
    const deleteBtn = document.getElementById('delete-spectrum-btn');
    if (deleteBtn) deleteBtn.style.display = 'none';
    
    // Удаляем спектр
    allFrequencies.splice(selectedSpectrumIndex, 1);
    allAmplitudes.splice(selectedSpectrumIndex, 1);
    fileNames.splice(selectedSpectrumIndex, 1);
    
    // Перестраиваем график
    rebuildPlot();
    selectedSpectrumIndex = -1;
}


// Функция для поиска индекса спектра по имени
function findSpectrumIndexByName(traceName) {
    for (let i = 0; i < fileNames.length; i++) {
        const fileName = truncateFileName(fileNames[i]) || `Файл ${i + 1}`;
        if (traceName === fileName || traceName === `Ср. ${fileName}`) {
            return i;
        }
    }
    return -1;
}

// Упрощенная функция rebuildPlot
function rebuildPlot() {
    plotCombinedSpectrum(
        allFrequencies,
        allAmplitudes,
        fileNames,
        [],
        [],
        [],
        false,
        [],
        `Спектры (${allFrequencies.length} файлов)`
    );
}

// Добавьте вызов createDeleteButton при загрузке
document.addEventListener('DOMContentLoaded', function() {
    createDeleteButton();
});


async function addMoreFiles() {
    const files = document.getElementById('files').files;
    if (files.length === 0) {
        alert('Пожалуйста, выберите файлы для добавления');
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

        if (!response.ok) {
            throw new Error(`Ошибка сервера: ${response.status}`);
        }

        const result = await response.json();

        if (result.frequencies && result.amplitudes) {
            // Добавляем новые данные к существующим
            const newFrequencies = result.frequencies.map(arr => arr.map(Number));
            const newAmplitudes = result.amplitudes.map(arr => arr.map(Number));
            const newFileNames = result.files;

            allFrequencies = [...allFrequencies, ...newFrequencies];
            allAmplitudes = [...allAmplitudes, ...newAmplitudes];
            fileNames = [...fileNames, ...newFileNames];

            // Обновляем график
            if (document.getElementById('spectrum_plot')) {
                plotCombinedSpectrum(
                    allFrequencies, 
                    allAmplitudes, 
                    fileNames, 
                    new Array(allFrequencies.length).fill([]),
                    [], // mean_amplitude
                    [], // std_amplitude
                    false, 
                    [], // boxplotStats
                    "Спектры (" + allFrequencies.length + " файлов)"
                );
            }

            alert(`Добавлено ${result.files.length} файлов. Всего: ${fileNames.length} файлов`);
        } else {
            throw new Error(result.error || 'Неизвестная ошибка при загрузке');
        }
    } catch (error) {
        console.error('Ошибка добавления файлов:', error);
        alert('Ошибка: ' + error.message);
    }
}

//функция для очистки всех спектров
function clearAllSpectra() {
    if (allFrequencies.length === 0) {
        alert('Нет спектров для очистки');
        return;
    }
    
    if (confirm(`Очистить все ${allFrequencies.length} спектров?`)) {
        allFrequencies = [];
        allAmplitudes = [];
        fileNames = [];
        processedData = {
            frequencies: [],
            amplitudes: [],
            fileNames: [],
            params: {}
        };
        
        // Очищаем график
        Plotly.purge('spectrum_plot');
        document.getElementById('spectrum_plot').innerHTML = '';
        
        alert('Все спектры очищены');
    }
}



























async function analyzeWithAI(spectrumIndex = 0) {
    if (allFrequencies.length === 0) {
        alert("Нет данных для анализа");
        return;
    }

    const spectrumType = prompt("Тип спектра (Raman, FTIR, UV-Vis и т.д.):", "Raman");
    const additionalContext = prompt("Дополнительная информация о образце:", "");

    try {
        const analysisData = {
            frequencies: allFrequencies[spectrumIndex],
            amplitudes: allAmplitudes[spectrumIndex],
            spectrum_type: spectrumType,
            additional_context: additionalContext
        };

        const response = await fetch('/analyze_spectrum', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(analysisData),
        });

        if (!response.ok) throw new Error('Ошибка анализа');

        const result = await response.json();
        
        // Отображение результатов анализа
        showAnalysisModal(result.analysis);
        
    } catch (error) {
        console.error("Ошибка анализа:", error);
        alert("Ошибка анализа: " + error.message);
    }
}

function showAnalysisModal(content) {
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        z-index: 10000;
        max-width: 80%;
        max-height: 80%;
        overflow: auto;
    `;
    
    modal.innerHTML = `
        <h3>Анализ DeepSeek AI</h3>
        <div style="margin: 15px 0; line-height: 1.6;">${content}</div>
        <button onclick="this.parentElement.remove()" style="padding: 8px 16px; background: #4299e1; color: white; border: none; border-radius: 5px; cursor: pointer;">
            Закрыть
        </button>
    `;
    
    document.body.appendChild(modal);
}