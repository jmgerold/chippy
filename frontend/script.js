document.addEventListener('DOMContentLoaded', () => {
    const tableHeaders = document.getElementById('table-headers');
    const tableBody = document.getElementById('table-body');
    const searchButton = document.getElementById('search-button');
    const searchBox = document.getElementById('search-box');
    const statusEl = document.getElementById('status');
    const progressCard = document.getElementById('progress-card');
    const progressStatus = document.getElementById('progress-status');
    const processedFiles = document.getElementById('processed-files');
    const totalFiles = document.getElementById('total-files');
    const processedTables = document.getElementById('processed-tables');
    const totalTables = document.getElementById('total-tables');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const currentFileEl = document.getElementById('current-file');
    const errorList = document.getElementById('error-list');
    const errorItems = document.getElementById('error-items');
    const relevantTables = document.getElementById('relevant-tables');
    const currentTable = document.getElementById('current-table');
    
    let columns = [];
    let nextColumnNumber = 1;
    let pollInterval = null;
    let currentTaskId = null;

    function updateProgressUI(progress) {
        console.log('Updating progress UI:', progress);
        
        // Update main message
        if (progress.message) {
            statusEl.textContent = progress.message;
        }
        
        // Update status badge
        const status = progress.status || 'processing';
        let displayStatus = status.charAt(0).toUpperCase() + status.slice(1).replace(/_/g, ' ');
        progressStatus.textContent = displayStatus;
        
        // Map status to appropriate CSS class
        let statusClass = 'processing';
        if (status === 'completed') statusClass = 'completed';
        else if (status === 'error') statusClass = 'error';
        progressStatus.className = `progress-status ${statusClass}`;
        
        // Update counts
        processedFiles.textContent = progress.processed_files || 0;
        totalFiles.textContent = progress.total_files || 0;
        processedTables.textContent = progress.processed_tables || 0;
        totalTables.textContent = progress.total_tables || 0;
        relevantTables.textContent = progress.relevant_tables || 0;
        
        // Update current action
        if (progress.current_action) {
            currentTable.textContent = progress.current_action;
            currentFileEl.style.display = 'block';
            currentFileEl.textContent = `Currently: ${progress.current_action}`;
        } else {
            currentTable.textContent = '-';
            currentFileEl.style.display = 'none';
        }
        
        // Update progress bar
        const percentage = progress.percentage || 0;
        progressBarFill.style.width = `${percentage}%`;
        
        // Update errors
        if (progress.errors && progress.errors.length > 0) {
            errorItems.innerHTML = progress.errors.map(err => 
                `<div class="error-item">• ${err}</div>`
            ).join('');
            errorList.style.display = 'block';
        } else {
            errorList.style.display = 'none';
        }
        
        // Handle completion
        if (status === 'completed') {
            console.log('Task completed, downloading CSV...');
            // Download the CSV automatically
            if (currentTaskId) {
                downloadCSV(currentTaskId);
            }
            
            // Hide progress card after a delay
            setTimeout(() => {
                progressCard.classList.remove('active');
            }, 3000);
        } else if (status === 'error') {
            // Hide on error too
            setTimeout(() => {
                progressCard.classList.remove('active');
            }, 5000);
        }
    }

    async function pollProgress(taskId) {
        try {
            const response = await fetch(`/api/progress/${taskId}`);
            const progress = await response.json();
            
            if (progress.status === 'not_found') {
                console.log('Task not found, stopping polling');
                stopPolling();
                return;
            }
            
            updateProgressUI(progress);
            
            // Stop polling when done
            if (progress.status === 'completed' || progress.status === 'error') {
                console.log('Task finished, stopping polling');
                stopPolling();
            }
        } catch (error) {
            console.error('Error polling progress:', error);
        }
    }

    function startPolling(taskId) {
        console.log('Starting polling for task:', taskId);
        currentTaskId = taskId;
        
        // Show progress card immediately
        progressCard.classList.add('active');
        
        // Reset progress values
        processedFiles.textContent = '0';
        totalFiles.textContent = '0';
        processedTables.textContent = '0';
        totalTables.textContent = '0';
        relevantTables.textContent = '0';
        currentTable.textContent = '-';
        progressBarFill.style.width = '0%';
        errorItems.innerHTML = '';
        errorList.style.display = 'none';
        
        // Poll immediately, then every 500ms
        pollProgress(taskId);
        pollInterval = setInterval(() => pollProgress(taskId), 500);
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    async function downloadCSV(taskId) {
        try {
            const response = await fetch(`/api/download/${taskId}`);
            if (!response.ok) {
                console.error('Failed to download CSV');
                return;
            }
            
            const csvText = await response.text();
            console.log('CSV downloaded, length:', csvText.length);
            
            // Parse and display the data
            const parsedData = parseCSV(csvText);
            
            // Update columns based on CSV header
            if (parsedData.length > 0) {
                const header = Object.keys(parsedData[0]);
                const existingTypes = new Map(columns.map(c => [c.name, c.type]));
                columns = header.map(name => ({
                    name,
                    type: existingTypes.get(name) || 'TEXT'
                }));
            }
            
            // Render the table with the data
            renderHeaders();
            renderBody(parsedData);
            
            // Update status
            statusEl.textContent = parsedData.length > 0 
                ? `✅ Loaded ${parsedData.length} rows from extraction.` 
                : '✅ Extraction completed but no matching data found.';
            
            // Also trigger a download for the user
            const blob = new Blob([csvText], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'patent_tables.csv';
            a.click();
            URL.revokeObjectURL(url);
            
        } catch (error) {
            console.error('Error downloading CSV:', error);
            statusEl.textContent = '❌ Failed to download results';
        }
    }

    function handleRename(span, oldName) {
        const input = document.createElement('input');
        input.type = 'text';
        input.value = oldName;
        span.replaceWith(input);
        input.focus();

        const finishEditing = () => {
            const newName = input.value.trim();
            if (newName && newName !== oldName) {
                const oldCol = columns.find(c => c.name === oldName);
                if (oldCol) {
                    if (!columns.some(c => c.name.toLowerCase() === newName.toLowerCase())) {
                        oldCol.name = newName;
                    } else {
                        alert('Column name must be unique.');
                    }
                }
            }
            render(); // Re-render to show updated header or revert
        };

        input.addEventListener('blur', finishEditing);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                finishEditing();
            } else if (e.key === 'Escape') {
                input.value = oldName; // Revert changes
                finishEditing();
            }
        });
    }

    function createColumnHeader({ name, type }) {
        const th = document.createElement('th');
        const headerContent = document.createElement('div');
        headerContent.className = 'header-content';
        
        const nameSpan = document.createElement('span');
        nameSpan.textContent = name;
        nameSpan.addEventListener('click', () => handleRename(nameSpan, name));

        const select = document.createElement('select');
        select.innerHTML = `
            <option value="TEXT" ${type === 'TEXT' ? 'selected' : ''}>TEXT</option>
            <option value="NUMERIC" ${type === 'NUMERIC' ? 'selected' : ''}>NUMERIC</option>
        `;
        select.addEventListener('click', (e) => e.stopPropagation());
        select.addEventListener('change', (e) => {
            const col = columns.find(c => c.name === name);
            if (col) {
                col.type = e.target.value;
            }
        });

        headerContent.appendChild(nameSpan);
        headerContent.appendChild(select);
        th.appendChild(headerContent);

        return th;
    }

    function renderHeaders() {
        tableHeaders.innerHTML = '';
        columns.forEach(col => {
            const header = createColumnHeader(col);
            tableHeaders.appendChild(header);
        });

        const addColumnCell = document.createElement('th');
        const addColumnBtn = document.createElement('button');
        addColumnBtn.textContent = '+';
        addColumnBtn.id = 'add-column-btn';
        addColumnBtn.title = 'Add new column';
        addColumnBtn.addEventListener('click', () => {
            let newColName;
            let i = nextColumnNumber;
            do {
                newColName = `Column ${i++}`;
            } while (columns.some(c => c.name === newColName));
            nextColumnNumber = i;
            
            columns.push({ name: newColName, type: 'TEXT' });
            render();
        });
        addColumnCell.appendChild(addColumnBtn);
        tableHeaders.appendChild(addColumnCell);
    }

    function renderBody(data = []) {
        tableBody.innerHTML = '';
        const numRows = data.length > 0 ? data.length : 10;
        const columnNames = columns.map(c => c.name);

        for (let i = 0; i < numRows; i++) {
            const tr = document.createElement('tr');
            const rowData = data[i] || {};
            columnNames.forEach(colName => {
                const td = document.createElement('td');
                td.textContent = rowData[colName] || '...';
                tr.appendChild(td);
            });
            // Empty cell for the '+' button column
            tr.appendChild(document.createElement('td')); 
            tableBody.appendChild(tr);
        }
    }

    function render() {
        renderHeaders();
        renderBody();
    }

    function parseCSV(text) {
        if (!text || text.trim() === '') return [];
        
        const lines = text.trim().split('\n');
        if (lines.length === 0) return [];
        
        // Parse header
        const header = parseCSVLine(lines[0]);
        const data = [];
        
        // Parse data rows
        for (let i = 1; i < lines.length; i++) {
            if (lines[i].trim() === '') continue;
            
            const values = parseCSVLine(lines[i]);
            const row = {};
            
            for (let j = 0; j < header.length; j++) {
                row[header[j]] = values[j] || '';
            }
            data.push(row);
        }
        
        return data;
    }

    function parseCSVLine(line) {
        const values = [];
        let current = '';
        let inQuotes = false;
        
        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            const nextChar = line[i + 1];
            
            if (char === '"') {
                if (inQuotes && nextChar === '"') {
                    // Escaped quote
                    current += '"';
                    i++; // Skip next quote
                } else {
                    // Toggle quote mode
                    inQuotes = !inQuotes;
                }
            } else if (char === ',' && !inQuotes) {
                // End of field
                values.push(current.trim());
                current = '';
            } else {
                current += char;
            }
        }
        
        // Don't forget the last field
        values.push(current.trim());
        
        return values;
    }

    async function handleSearch() {
        const query = searchBox.value.trim();
        const currentColumns = columns.map(c => c.name);
        const columnTypes = columns.map(c => c.type);

        if (!query || currentColumns.length === 0) {
            statusEl.textContent = "❌ Please provide a search query and at least one column.";
            return;
        }

        // Stop any existing polling
        stopPolling();

        // Disable search button during processing
        searchButton.disabled = true;
        statusEl.textContent = "Starting extraction...";
        
        // Clear any previous data
        renderBody([]);

        try {
            // Start the extraction
            const response = await fetch("/api/extract", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, columns: currentColumns, types: columnTypes }),
            });

            if (!response.ok) {
                const { detail } = await response.json();
                statusEl.textContent = `❌ ${detail || "Unknown error"}`;
                return;
            }

            const result = await response.json();
            console.log('Extraction started:', result);
            
            // Start polling for progress
            if (result.task_id) {
                startPolling(result.task_id);
            } else {
                statusEl.textContent = "❌ No task ID received";
            }

        } catch (err) {
            console.error(err);
            statusEl.textContent = "❌ Failed to reach backend";
            progressCard.classList.remove('active');
        } finally {
            searchButton.disabled = false;
        }
    }

    function init() {
        columns = [{ name: "sequence", type: "TEXT" }, { name: "UTC_expression", type: "TEXT" }];
        nextColumnNumber = columns.length + 1;
        render();
        searchButton.addEventListener('click', handleSearch);
        
        // Allow Enter key to trigger search
        searchBox.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !searchButton.disabled) {
                handleSearch();
            }
        });
    }

    init();
});