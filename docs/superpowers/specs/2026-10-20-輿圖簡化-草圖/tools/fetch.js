const fs = require("fs");
const base = "http://127.0.0.1:7892";
const [login, password] = fs.readFileSync(__dirname + "/login.txt", "utf8").split(/\r?\n/);
(async () => {
  const r = await fetch(base + "/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ login, password }) });
  const cookie = (r.headers.get("set-cookie") || "").split(";")[0];
  for (const ep of ["base", "state"]) {
    const j = await (await fetch(base + "/api/map/" + ep, { headers: { cookie } })).json();
    fs.writeFileSync(__dirname + "/map_" + ep + ".json", JSON.stringify(j));
    console.log(ep, Object.keys(j).join(","));
  }
})();
