document.addEventListener('DOMContentLoaded', () => {
    const tableHeaders = document.getElementById('table-headers');
    const tableBody = document.getElementById('table-body');
    const searchButton = document.getElementById('search-button');
    const searchBox = document.getElementById('search-box');
    const statusEl = document.getElementById('status');
    let columns = [];
    let nextColumnNumber = 1;

    function handleRename(span, oldName) {
        const input = document.createElement('input');
        input.type = 'text';
        input.value = oldName;
        span.replaceWith(input);
        input.focus();

        const finishEditing = () => {
            const newName = input.value.trim();
            if (newName && newName !== oldName) {
                const oldIndex = columns.indexOf(oldName);
                if (oldIndex > -1) {
                    if (!columns.map(c => c.toLowerCase()).includes(newName.toLowerCase())) {
                        columns[oldIndex] = newName;
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

    function createColumnHeader(name) {
        const th = document.createElement('th');
        const headerContent = document.createElement('div');
        headerContent.className = 'header-content';
        
        const nameSpan = document.createElement('span');
        nameSpan.textContent = name;
        nameSpan.addEventListener('click', () => handleRename(nameSpan, name));

        const select = document.createElement('select');
        select.innerHTML = `
            <option value="TEXT">TEXT</option>
            <option value="NUMERIC">NUMERIC</option>
        `;
        select.addEventListener('click', (e) => e.stopPropagation()); // prevent sorting or other header actions

        headerContent.appendChild(nameSpan);
        headerContent.appendChild(select);
        th.appendChild(headerContent);

        return th;
    }

    function renderHeaders() {
        tableHeaders.innerHTML = '';
        columns.forEach(colName => {
            const header = createColumnHeader(colName);
            tableHeaders.appendChild(header);
        });

        const addColumnCell = document.createElement('th');
        const addColumnBtn = document.createElement('button');
        addColumnBtn.textContent = '+';
        addColumnBtn.id = 'add-column-btn';
        addColumnBtn.title = 'Add new column';
        addColumnBtn.addEventListener('click', () => {
            let newColName;
            do {
                newColName = `Column ${nextColumnNumber++}`;
            } while (columns.includes(newColName));
            
            columns.push(newColName);
            render();
        });
        addColumnCell.appendChild(addColumnBtn);
        tableHeaders.appendChild(addColumnCell);
    }

    function renderBody() {
        tableBody.innerHTML = '';
        const numRows = 10;
        for (let i = 0; i < numRows; i++) {
            const tr = document.createElement('tr');
            columns.forEach(() => {
                const td = document.createElement('td');
                td.textContent = '...';
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
        statusEl.textContent = "Processing… this may take a moment";
        const query = searchBox.value.trim();
        const currentColumns = [...columns];
        const columnTypes = Array.from(tableHeaders.querySelectorAll('select')).map(s => s.value);

        if (!query || currentColumns.length === 0) {
            statusEl.textContent = "❌ Please provide a search query and at least one column.";
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
                statusEl.textContent = `❌ ${detail || "Unknown error"}`;
                return;
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "patent_tables.csv";
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            statusEl.textContent = "✅ CSV downloaded!";
        } catch (err) {
            console.error(err);
            statusEl.textContent = "❌ Failed to reach backend";
        }
    }

    function init() {
        columns = ["sequence", "UTC expression"];
        nextColumnNumber = columns.length + 1;
        render();
        searchButton.addEventListener('click', handleSearch);
    }

    init();
});