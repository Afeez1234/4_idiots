document.addEventListener('DOMContentLoaded', function () {
  const searchInputs = document.querySelectorAll('[data-table-filter]');

  searchInputs.forEach(function (input) {
    const tableId = input.getAttribute('data-table-filter');
    const table = document.getElementById(tableId);

    if (!table) return;

    const rows = table.querySelectorAll('tbody tr');

    input.addEventListener('input', function () {
      const term = this.value.toLowerCase().trim();

      rows.forEach(function (row) {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(term) ? '' : 'none';
      });
    });
  });

  const historyDateFilter = document.getElementById('history-date-filter');
  const historyRows = document.querySelectorAll('#history-table tbody tr');

  if (historyDateFilter && historyRows.length) {
    historyDateFilter.addEventListener('change', function () {
      const selectedDate = this.value;

      historyRows.forEach(function (row) {
        const rowDate = row.querySelector('td').textContent.trim();
        row.style.display = selectedDate ? (rowDate === selectedDate ? '' : 'none') : '';
      });
    });
  }
});
