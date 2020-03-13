.mode columns
.headers on
WITH
t1 AS (SELECT dt, temp FROM temperature WHERE id = 'C1' ORDER BY dt DESC LIMIT 60),
t2 AS (SELECT dt, temp FROM temperature WHERE id = 'C2' ORDER BY dt DESC LIMIT 60),
t3 AS (SELECT dt, temp FROM temperature WHERE id = 'C3' ORDER BY dt DESC LIMIT 60),
t4 AS (SELECT dt, temp FROM temperature WHERE id = 'C4' ORDER BY dt DESC LIMIT 60),
t5 AS (SELECT dt, temp FROM temperature WHERE id = 'C5' ORDER BY dt DESC LIMIT 60)
SELECT strftime('%H:%M:%S', t1.dt) "time",
  printf('%0.1f', t1.temp) "t1",
  printf('%0.1f', t2.temp) "t2",
  printf('%0.1f', t3.temp) "t3",
  printf('%0.1f', t4.temp) "t4",
  printf('%0.1f', t5.temp) "t5"
FROM t1
LEFT JOIN t2 USING (dt)
LEFT JOIN t3 USING (dt)
LEFT JOIN t4 USING (dt)
LEFT JOIN t5 USING (dt)
ORDER BY dt;