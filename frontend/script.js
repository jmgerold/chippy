document.addEventListener('DOMContentLoaded', () => {
    const tableHeaders = document.getElementById('table-headers');
    const tableBody = document.getElementById('table-body');
    const searchButton = document.getElementById('search-button');
    const searchBox = document.getElementById('search-box');
    const statusEl = document.getElementById('status');
    let columns = [];
    let nextColumnNumber = 1;
    let loadingInterval;

    function startLoadingAnimation() {
        let dots = '.';
        statusEl.textContent = `Processing${dots}`;
        loadingInterval = setInterval(() => {
            dots = dots.length < 3 ? dots + '.' : '.';
            statusEl.textContent = `Processing${dots}`;
        }, 500);
    }

    function stopLoadingAnimation(message = '') {
        clearInterval(loadingInterval);
        statusEl.textContent = message;
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

    async function handleSearch() {
        startLoadingAnimation();
        const query = searchBox.value.trim();
        const currentColumns = columns.map(c => c.name);
        const columnTypes = columns.map(c => c.type);

        if (!query || currentColumns.length === 0) {
            stopLoadingAnimation("❌ Please provide a search query and at least one column.");
            return;
        }

        try {
            const response = await fetch("/api/extract", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, columns: currentColumns, types: columnTypes }),
            });

            if (!response.ok) {
                const { detail } = await response.json();
                stopLoadingAnimation(`❌ ${detail || "Unknown error"}`);
                return;
            }

            const csvText = await response.text();
            const parsedData = parseCSV(csvText);
            
            // Update columns based on header from CSV
            if (parsedData.length > 0) {
                const header = Object.keys(parsedData[0]);
                const existingTypes = new Map(columns.map(c => [c.name, c.type]));
                columns = header.map(name => ({
                    name,
                    type: existingTypes.get(name) || 'TEXT'
                }));
            }

            renderHeaders();
            renderBody(parsedData);
            stopLoadingAnimation(parsedData.length > 0 ? `✅ Loaded ${parsedData.length} rows.` : '✅ No results found.');

        } catch (err) {
            console.error(err);
            stopLoadingAnimation("❌ Failed to reach backend");
        }
    }
    
    function parseCSV(text) {
        if (!text) return [];
        const lines = text.trim().split('\n');
        const header = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
        const data = [];
        for (let i = 1; i < lines.length; i++) {
            if (lines[i].trim() === '') continue;
            const values = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
            const row = {};
            for (let j = 0; j < header.length; j++) {
                row[header[j]] = values[j];
            }
            data.push(row);
        }
        return data;
    }

    function init() {
        columns = [{ name: "sequence", type: "TEXT" }, { name: "UTC expression", type: "TEXT" }];
        nextColumnNumber = columns.length + 1;
        render();
        searchButton.addEventListener('click', handleSearch);
    }

    init();
});