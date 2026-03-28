/**
 * Creates a test CSV string in memory for import tests.
 * @param {Array<{name: string, username: string, password: string, url: string}>} rows
 * @returns {string} CSV content
 */
export function makeTestCSV(rows) {
  const header = 'name,username,password,url\n'
  const body = rows.map(r => `${r.name},${r.username},${r.password},${r.url}`).join('\n')
  return header + body
}
