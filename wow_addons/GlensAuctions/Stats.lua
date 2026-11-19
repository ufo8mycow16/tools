-- Glen's Auctions - price history and market value.
-- Each item keeps one entry per day: { day, lowest, typical, quantity on sale, listings }.
-- "Typical" is the quantity-weighted median of the cheaper half of everything listed, so a few
-- silly listings (copper ore at 50g) don't drag it around. Market value blends the recent days,
-- newer days counting more - the same idea as Auctioneer's Simple / Std Dev / Histogram stats.
local _, GA = ...

local floor = math.floor

-- prices: array of { unit = copper per item, qty = how many at that price }
function GA:Summarise(prices)
	if not prices or #prices == 0 then return nil end
	table.sort(prices, function(a, b) return a.unit < b.unit end)
	local total = 0
	for i = 1, #prices do total = total + prices[i].qty end
	if total <= 0 then return nil end
	-- weighted median of the cheapest half (by quantity)
	local half = total / 2
	local target = half / 2
	local run, typical = 0, prices[1].unit
	for i = 1, #prices do
		run = run + prices[i].qty
		if run >= target then typical = prices[i].unit; break end
	end
	return prices[1].unit, typical, total, #prices
end

function GA:Record(key, prices, name)
	if not key or not self.realm then return end
	local low, typical, qty, n = self:Summarise(prices)
	if not low then return end
	local items = self.realm.items
	local rec = items[key]
	if not rec then rec = { d = {} }; items[key] = rec end
	if name then rec.name = name end
	local today = self:Today()
	local d = rec.d
	local last = d[#d]
	local entry = { today, floor(low), floor(typical), qty, n }
	if last and last[1] == today then d[#d] = entry else d[#d + 1] = entry end
	-- trim old days
	local keep = today - (self.set.historyDays or 30)
	while d[1] and d[1][1] < keep do table.remove(d, 1) end
	rec.t = time()
end

-- Market value from the last 14 days of typical prices, newer days weighted more.
function GA:Market(key)
	local rec = key and self.realm and self.realm.items[key]
	if not rec or not rec.d or #rec.d == 0 then return nil end
	local today = self:Today()
	local pts, wsum = {}, 0
	local qsum, days = 0, 0
	for i = #rec.d, 1, -1 do
		local e = rec.d[i]
		local age = today - e[1]
		if age > 14 then break end
		local w = 0.85 ^ age
		pts[#pts + 1] = { v = e[3], w = w }
		wsum = wsum + w
		qsum = qsum + e[4]
		days = days + 1
	end
	if days == 0 then
		-- nothing recent: fall back to the newest we have, flagged as old
		local e = rec.d[#rec.d]
		return e[3], nil, 0, e[4], e[1]
	end
	table.sort(pts, function(a, b) return a.v < b.v end)
	local run, market = 0, pts[1].v
	for i = 1, #pts do
		run = run + pts[i].w
		if run >= wsum / 2 then market = pts[i].v; break end
	end
	local newest = rec.d[#rec.d]
	local todayLow = (newest[1] == today) and newest[2] or nil
	return market, todayLow, days, floor(qsum / days + 0.5), newest[1]
end

function GA:MarketForLink(link)
	local key, id = self:KeyFromLink(link)
	local m, low, days, qty, newest = self:Market(key)
	if not m and key ~= tostring(id) then
		-- no data for this exact suffix: use the plain item
		m, low, days, qty, newest = self:Market(tostring(id))
	end
	return m, low, days, qty, newest
end
