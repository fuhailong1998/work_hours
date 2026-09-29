// A cycle is named after the month containing its final day (the 24th).
export function hoursCycle(today, offset = 0) {
  const [year, month] = today.split('-').map(Number);
  const endMonth = month - 1 + offset;
  const start = new Date(Date.UTC(year, endMonth - 1, 25)).toISOString().slice(0, 10);
  const end = new Date(Date.UTC(year, endMonth, 24)).toISOString().slice(0, 10);
  return {start, end, label: `${end.slice(0,4)} 年 ${Number(end.slice(5,7))} 月工时周期`};
}
