.mode columns
.headers on
WITH
A AS (SELECT dt, state, duty FROM relay WHERE id = 'A' ORDER BY dt DESC LIMIT 1),
B AS (SELECT dt, state, duty FROM relay WHERE id = 'B' ORDER BY dt DESC LIMIT 1),
C AS (SELECT dt, state, duty FROM relay WHERE id = 'C' ORDER BY dt DESC LIMIT 1),
D AS (SELECT dt, state, duty FROM relay WHERE id = 'D' ORDER BY dt DESC LIMIT 1)
SELECT strftime('%H:%M:%S', A.dt) "time",
  printf('%.2f', A.duty) "duty_A",
  printf('%.2f', B.duty) "duty_B",
  printf('%.2f', C.duty) "duty_C",
  printf('%.2f', D.duty) "duty_D"
FROM A
LEFT JOIN B USING (dt)
LEFT JOIN C USING (dt)
LEFT JOIN D USING (dt)
ORDER BY dt;