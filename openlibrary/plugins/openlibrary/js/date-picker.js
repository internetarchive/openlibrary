/**
 * Replaces all text inputs with "date" in their name with Year/Month/Day dropdowns.
 * Works for editions, authors, and any other pages in Open Library.
 */
export function initSearchableDatePickers() {
    //console.log('DEBUG: initSearchableDatePickers running...');

    const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    const isLeapYear = (year) =>
        year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

    // Automatically find all text inputs with "date" in the name
    const dateInputs = Array.from(document.querySelectorAll('input[type="text"]'))
        .filter(input => /date/i.test(input.name));

    //console.log('DEBUG: Found date inputs:', dateInputs.map(i => i.name));

    dateInputs.forEach(originalInput => {
        //console.log(`DEBUG: Converting ${originalInput.name} to dropdowns...`);

        // Hide original input
        originalInput.type = 'hidden';
        originalInput.classList.add('date-picker-hidden-input');

        // Create container
        const container = document.createElement('div');
        container.className = 'date-picker-dropdowns';
        container.style.display = 'inline-flex';
        container.style.gap = '5px';

        if (originalInput.parentNode) {
            originalInput.parentNode.insertBefore(container, originalInput);
        }

        // Year dropdown
        const yearSelect = document.createElement('select');
        yearSelect.name = `${originalInput.name}_year`;

        const currentYear = new Date().getFullYear();
        const MIN_YEAR = 800; // you can change to 1000 or any year
        let yearOptions = '<option value="">Year</option>';
        for (let y = currentYear; y >= MIN_YEAR; y--) {
            yearOptions += `<option value="${y}">${y}</option>`;
        }
        yearSelect.innerHTML = yearOptions;

        // Month dropdown
        const monthSelect = document.createElement('select');
        monthSelect.name = `${originalInput.name}_month`;
        monthSelect.innerHTML = '<option value="">Month</option>';

        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        months.forEach((name,i) => {
            monthSelect.innerHTML += `<option value="${i+1}">${name}</option>`;
        });

        // Day dropdown
        const daySelect = document.createElement('select');
        daySelect.name = `${originalInput.name}_day`;
        daySelect.innerHTML = '<option value="">Day</option>';
        for (let d = 1; d <= 31; d++) {
            daySelect.innerHTML += `<option value="${d}">${d}</option>`;
        }

        container.appendChild(yearSelect);
        container.appendChild(monthSelect);
        container.appendChild(daySelect);

        // Update day options based on month/year
        const updateDayOptions = () => {
            const year = Number(yearSelect.value);
            const month = Number(monthSelect.value);
            if (!month) return;

            let daysInMonth = DAYS_IN_MONTH[month - 1];
            if (month === 2 && year && isLeapYear(year)) ++daysInMonth;

            const now = new Date();
            const isCurrentYear = year === now.getFullYear();
            const isCurrentMonth = isCurrentYear && month === now.getMonth() + 1;

            for (let i = 0; i < daySelect.options.length; i++) {
                const dayValue = Number(daySelect.options[i].value);
                if (!dayValue) continue;
                const isFutureDay = isCurrentMonth && dayValue > now.getDate();
                daySelect.options[i].disabled = dayValue > daysInMonth || isFutureDay;
                daySelect.options[i].classList.toggle('hidden', dayValue > daysInMonth);
            }

            if (Number(daySelect.value) > daysInMonth ||
            (isCurrentMonth && Number(daySelect.value) > now.getDate())) {
                daySelect.value = '';
            }
        };
        const updateFutureMonths = () => {
            const year = Number(yearSelect.value);
            const now = new Date();
            const isCurrentYear = year === now.getFullYear();

            for (let i = 0; i < monthSelect.options.length; i++) {
                const monthValue = Number(monthSelect.options[i].value);
                if (!monthValue) continue;
                monthSelect.options[i].disabled = isCurrentYear && monthValue > now.getMonth() + 1;
            }

            if (isCurrentYear && Number(monthSelect.value) > now.getMonth() + 1) {
                monthSelect.value = '';
                daySelect.value = '';
            }
        };
        // Update hidden input value
        const updateHiddenInput = () => {
            const year = yearSelect.value;
            const month = monthSelect.value;
            const day = daySelect.value;

            let dateStr = year || '';
            if (year && month) {
                dateStr += `-${String(month).padStart(2,'0')}`;
                if (day) dateStr += `-${String(day).padStart(2,'0')}`;
            }

            originalInput.value = dateStr;
            //console.log(`DEBUG: Date updated to: ${dateStr}`);
        };

        yearSelect.addEventListener('change', ()=>{ updateFutureMonths(); updateDayOptions(); updateHiddenInput(); });
        monthSelect.addEventListener('change', ()=>{ updateDayOptions(); updateHiddenInput(); });
        daySelect.addEventListener('change', updateHiddenInput);

        // Pre-fill from existing value
        if (originalInput.value) {
            const parts = originalInput.value.split('-');
            if (parts[0]) yearSelect.value = parts[0];
            if (parts[1]) monthSelect.value = parseInt(parts[1],10);
            if (parts[2]) daySelect.value = parseInt(parts[2],10);
            updateDayOptions();
        }
    });
}
