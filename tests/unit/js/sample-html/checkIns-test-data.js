export const checkInForm = `
<div class="check-in">
  <form class="check-in__form" action="">
    <input type="hidden" name="event_type" value="3">
    <input type="hidden" name="event_id" value="">
    <input type="hidden" name="edition_key" value="">
    <div class="check-in__inputs">
      <label class="check-in__label">Start Date:</label>
      <span>
        <label class="check-in__year-label">Year:</label>
        <select class="check-in__select" name="year">
          <option value="">Year</option>
          <option class="hidden show-if-local-year" value="$(year + 1)">$(year + 1)</option>
          <option value="2022">2022</option>
          <option value="2021">2021</option>
          <option value="2020">2020</option>
          <option value="2019">2019</option>
          <option value="2018">2018</option>
        </select>
      </span>
      <span>
        <label class="check-in__month-label">Month:</label>
        <select class="check-in__select" name="month" disabled>
          <option value="">Month</option>
          <option value="1">January</option>
          <option value="2">February</option>
          <option value="3">March</option>
          <option value="4">April</option>
          <option value="5">May</option>
          <option value="6">June</option>
          <option value="7">July</option>
          <option value="8">August</option>
          <option value="9">September</option>
          <option value="10">October</option>
          <option value="11">November</option>
          <option value="12">December</option>
        </select>
      </span>
      <span>
        <label class="check-in__day-label">Day:</label>
        <select class="check-in__select" name="day" disabled>
          <option value="">Day</option>
          <option value="1">1</option>
          <option value="2">2</option>
          <option value="3">3</option>
          <option value="4">4</option>
          <option value="5">5</option>
          <option value="6">6</option>
          <option value="7">7</option>
          <option value="8">8</option>
          <option value="9">9</option>
          <option value="10">10</option>
          <option value="11">11</option>
          <option value="12">12</option>
          <option value="13">13</option>
          <option value="14">14</option>
          <option value="15">15</option>
          <option value="16">16</option>
          <option value="17">17</option>
          <option value="18">18</option>
          <option value="19">19</option>
          <option value="20">20</option>
          <option value="21">21</option>
          <option value="22">22</option>
          <option value="23">23</option>
          <option value="24">24</option>
          <option value="25">25</option>
          <option value="26">26</option>
          <option value="27">27</option>
          <option value="28">28</option>
          <option value="29">29</option>
          <option value="30">30</option>
          <option value="31">31</option>
        </select>
      </span>
      <span>
        <a class="check-in__today" href="javascript:;">Today</a>
      </span>
    </div>
    <span class="check-in__actions">
      <button class="check-in__delete-btn cta-btn cta-btn--delete invisible">Delete Event</button>
      <button type="submit" class="check-in__submit-btn cta-btn cta-btn--shell" disabled>Submit</button>
    </span>
  </form>
</div>
`
