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
    let extractionData = []; // Store the final CSV data
    let tableProgressData = {}; // Store table-level progress
    let dotAnimationInterval = null;

    function startDotAnimation() {
        stopDotAnimation();
        let dotState = 0;
        dotAnimationInterval = setInterval(() => {
            dotState = (dotState + 1) % 3;
            const dots = '.'.repeat(dotState + 1);
            const loadingSpans = document.querySelectorAll('.status-badge.loading');

            if (loadingSpans.length === 0) {
                stopDotAnimation();
                return;
            }

            loadingSpans.forEach(span => {
                span.textContent = `Loading${dots}`;
            });
        }, 300);
    }

    function stopDotAnimation() {
        if (dotAnimationInterval) {
            clearInterval(dotAnimationInterval);
            dotAnimationInterval = null;
        }
    }

    function updateProgressUI(progress) {
        console.log('Updating progress UI:', progress);
        
        // If this is the first progress update with table info, build the table skeleton
        if (progress.tables && Object.keys(tableProgressData).length === 0 && Object.keys(progress.tables).length > 0) {
            console.log("Initializing progress table");
            tableProgressData = progress.tables;
            initializeProgressTable(tableProgressData);
        } 
        // For subsequent updates, update rows in-place
        else if (progress.tables && Object.keys(progress.tables).length > 0) {
            console.log("Updating progress table");
            updateProgressTable(progress.tables);
        }
        
        // Handle completion
        if (progress.status === 'completed') {
            console.log('Task completed, downloading CSV...');
            stopPolling();
            if (currentTaskId) {
                downloadCSV(currentTaskId);
            }
        } else if (progress.status === 'error') {
            statusEl.textContent = '❌ ' + (progress.message || 'Extraction failed');
            stopPolling();
        }
    }

    function initializeProgressTable(tables) {
        tableBody.innerHTML = '';
        const userColumns = columns.filter(c => c.name !== 'USPTO_ID' && c.name !== 'Table_No');
        
        const sortedTables = Object.values(tables).sort((a, b) => {
            if (a.uspto_id < b.uspto_id) return -1;
            if (a.uspto_id > b.uspto_id) return 1;
            return a.table_no - b.table_no;
        });

        sortedTables.forEach(table => {
            const tr = document.createElement('tr');
            tr.id = `row-${table.uid}`;
            
            // USPTO_ID cell
            const tdId = document.createElement('td');
            tdId.textContent = table.uspto_id;
            tr.appendChild(tdId);
            
            // Table_No cell
            const tdNum = document.createElement('td');
            tdNum.textContent = table.table_no;
            tr.appendChild(tdNum);

            // User-added columns
            userColumns.forEach(col => {
                const td = document.createElement('td');
                td.className = 'status-cell';
                td.dataset.columnName = col.name; // Tag cell for updates
                const loadingSpan = document.createElement('span');
                loadingSpan.className = 'status-badge loading';
                loadingSpan.textContent = 'Loading...';
                td.appendChild(loadingSpan);
                tr.appendChild(td);
            });

            // Empty cell for '+' button column
            const placeholderCell = document.createElement('td');
            tr.appendChild(placeholderCell);
            
            tableBody.appendChild(tr);
        });
    }

    function updateProgressTable(tables) {
        const userColumns = columns.filter(c => c.name !== 'USPTO_ID' && c.name !== 'Table_No');

        Object.values(tables).forEach(table => {
            const row = document.getElementById(`row-${table.uid}`);
            if (!row) return;

            // Only update if status has changed
            if (tableProgressData[table.uid]?.status !== table.status) {
                userColumns.forEach(col => {
                    const cell = row.querySelector(`td[data-column-name="${col.name}"]`);
                    if (cell) {
                        switch (table.status) {
                            case 'completed_relevant':
                                cell.innerHTML = `<span class="status-badge match">Match</span>`;
                                cell.className = 'status-cell';
                                break;
                            case 'completed_irrelevant':
                                cell.innerHTML = `<span class="status-badge miss">Miss</span>`;
                                cell.className = 'status-cell';
                                break;
                            case 'error':
                                cell.innerHTML = `<span class="status-badge miss">Miss</span>`;
                                cell.className = 'status-cell';
                                break;
                            // For 'pending' or 'processing', the spinner is already there
                        }
                    }
                });
            }
        });
        // Update the master copy of progress
        tableProgressData = tables;
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
        tableProgressData = {}; // Reset progress data
        
        // Show loading state in the main table immediately
        renderBody([]); // Clear table initially
        
        // Poll immediately, then every 500ms
        pollProgress(taskId);
        pollInterval = setInterval(() => pollProgress(taskId), 500);
        startDotAnimation();
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
        stopDotAnimation();
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
            
            // Store the final data and render the table
            extractionData = parsedData;
            renderHeaders();
            renderBody(extractionData);
            
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

        const leftGroup = document.createElement('div');
        leftGroup.style.display = 'flex';
        leftGroup.style.alignItems = 'center';

        const icon = document.createElement('i');
        icon.className = 'fa-solid fa-bars';
        icon.style.marginRight = '0.5rem';
        icon.style.cursor = 'grab';
        
        const nameSpan = document.createElement('span');
        nameSpan.textContent = name;
        
        // Make USPTO_ID and Table_No columns non-editable
        const isFixedColumn = name === 'USPTO_ID' || name === 'Table_No';
        if (!isFixedColumn) {
            nameSpan.addEventListener('click', () => handleRename(nameSpan, name));
        } else {
            nameSpan.style.cursor = 'default';
            nameSpan.style.fontWeight = 'bold';
            nameSpan.style.color = '#666';
        }

        leftGroup.appendChild(icon);
        leftGroup.appendChild(nameSpan);

        // Only add type selector for non-fixed columns
        if (!isFixedColumn) {
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
            headerContent.appendChild(leftGroup);
            headerContent.appendChild(select);
        } else {
            // For fixed columns, just show the name without dropdown
            headerContent.appendChild(leftGroup);
        }
        
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
        const columnNames = columns.map(c => c.name);

        // If we have final data, render it
        if (data.length > 0) {
            data.forEach(rowData => {
                const tr = document.createElement('tr');
                columnNames.forEach(colName => {
                    const td = document.createElement('td');
                    td.textContent = rowData[colName] || '';
                    tr.appendChild(td);
                });
                // Empty cell for the '+' button column
                const placeholderCell = document.createElement('td');
                tr.appendChild(placeholderCell);
                tableBody.appendChild(tr);
            });
        } 
        // If there's no task and no data, show empty placeholder rows.
        else if (!currentTaskId) {
            const numRows = 10;
            for (let i = 0; i < numRows; i++) {
                const tr = document.createElement('tr');
                columnNames.forEach(colName => {
                    const td = document.createElement('td');
                    td.textContent = '...';
                    tr.appendChild(td);
                });
                // Empty cell for the '+' button column
                const placeholderCell = document.createElement('td');
                tr.appendChild(placeholderCell);
                tableBody.appendChild(tr);
            }
        }
        // If a task is running, the progress table is managed elsewhere (initializeProgressTable).
        // A temporary message is shown in handleSearch, so this function doesn't need to do anything.
    }

    function render() {
        renderHeaders();
        renderBody(extractionData);
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
        currentTaskId = null;
        extractionData = [];
        tableProgressData = {}; // clear progress data

        // Disable search button and show initial message
        searchButton.disabled = true;
        statusEl.textContent = "";
        tableBody.innerHTML = ``;

        try {
            // Start the extraction and get the initial table list
            const response = await fetch("/api/extract", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, columns: currentColumns, types: columnTypes }),
            });

            if (!response.ok) {
                const { detail } = await response.json();
                statusEl.textContent = `❌ ${detail || "Unknown error"}`;
                searchButton.disabled = false;
                renderBody([]); // Show empty state
                return;
            }

            const result = await response.json();
            console.log('Extraction started:', result);
            
            // The response now contains the initial table list
            if (result.tables && Object.keys(result.tables).length > 0) {
                tableProgressData = result.tables;
                initializeProgressTable(tableProgressData);
            } else {
                // If no tables are found, show the message and stop
                statusEl.textContent = result.message || "No relevant tables found.";
                searchButton.disabled = false;
                renderBody([]); // Show empty state
                return;
            }
            
            // Start polling for progress if the task is not already complete
            if (result.status !== 'completed' && result.task_id) {
                startPolling(result.task_id);
            } else {
                // This case handles if discovery found nothing and completed immediately
                statusEl.textContent = result.message;
                searchButton.disabled = false;
            }

        } catch (err) {
            console.error(err);
            statusEl.textContent = "❌ Failed to reach backend";
            searchButton.disabled = false;
            renderBody([]); // Show empty state
        }
        // The finally block is removed because the button is re-enabled in specific paths
    }

    function init() {
        columns = [{ name: "USPTO_ID", type: "TEXT" }, { name: "Table_No", type: "TEXT" }];
        nextColumnNumber = 1; // Start user columns from 1
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