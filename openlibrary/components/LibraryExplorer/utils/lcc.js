/**
 * Largely copied from openlibrary\utils\lcc.py :(
 * KEEP IN SYNC!
 */

const LCC_PARTS_RE = new RegExp(
  String.raw`
        ^
        (?<letters>[A-HJ-NP-VWZ][A-Z-]{0,2})
        \s?
        (?<number>\d{1,4}(\.\d+)?)?
        (?<cutter1>\s*\.\s*[^\d\s\[]{1,3}\d*\S*)?
        (?<rest>\s.*)?
        $`.replace(/\s/g, ''),
  'i');

export function short_lcc_to_sortable_lcc(lcc) {
  const m = clean_raw_lcc(lcc).match(LCC_PARTS_RE);
  if (!m) return null

  const letters = m.groups.letters.toUpperCase().padEnd(3, '-');
  const number = parseFloat(m.groups.number || 0);
  const cutter1 = m.groups.cutter1 ? `.${m.groups.cutter1.replace(/^[ .]+/, '')}` : '';
  const rest = m.groups.rest ? ` ${m.groups.rest}` : '';

  // There will often be a CPB Box No (whatever that is) in the LCC field;
  // E.g. "CPB Box no. 1516 vol. 17"
  // Although this might be useful to search by, it's not really an LCC,
  // so considering it invalid here.
  if (letters === 'CPB') return null;

  return `${letters}${number.toFixed(8).padStart(13, '0')}${cutter1}${rest}`;
}

/**
 * @param {string} lcc
 */
export function sortable_lcc_to_short_lcc(lcc) {
  const m = lcc.match(LCC_PARTS_RE);
  const parts = {
    letters: m.groups.letters.replace(/-+/, ''),
    number: parseFloat(m.groups.number),
    cutter1: m.groups.cutter1 ? m.groups.cutter1.trim() : '',
    rest: m.groups.rest ? ` ${m.groups.rest}` : ''
  }
  return `${parts.letters}${parts.number}${parts.cutter1}${parts.rest}`;
}


/**
 * Remove noise in lcc before matching to LCC_PARTS_RE
 * @param {string} raw_lcc
 * @return {string}
 */
export function clean_raw_lcc(raw_lcc) {
  let lcc = raw_lcc.replace(/\\/g, ' ').trim();
  if ((lcc.startsWith('[') && lcc.endsWith(']')) || (lcc.startsWith('(') && lcc.endsWith(')'))) {
    lcc = lcc.slice(1, -1);
  }
  return lcc
}
