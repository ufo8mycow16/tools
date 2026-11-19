-- Glen's Auctions - core: namespace, saved data, events, helpers.
-- Modelled on the classic Auctioneer suite, written from scratch for WoW Forever's (modern) auction house.
local ADDON, GA = ...
_G.GlensAuctions = GA

GA.VERSION = "0.1"
GA.BUILD = 1
GA.TEX = "Interface\\AddOns\\GlensAuctions\\Textures\\"
GA.COLOR = "|cff5b86e5"

-- ---------------------------------------------------------------- events
local ev = CreateFrame("Frame")
local handlers = {}
function GA:On(event, fn)
	if not handlers[event] then
		handlers[event] = {}
		-- an event this client doesn't have must not break the whole addon
		local ok = pcall(ev.RegisterEvent, ev, event)
		if not ok then handlers[event].missing = true end
	end
	table.insert(handlers[event], fn)
end
ev:SetScript("OnEvent", function(_, event, ...)
	local list = handlers[event]
	if not list then return end
	for i = 1, #list do
		local ok, err = pcall(list[i], ...)
		if not ok then GA:Print("|cffff5555error|r in " .. event .. ": " .. tostring(err)) end
	end
end)

-- simple internal callbacks (UI refreshes etc.)
local cbs = {}
function GA:Listen(name, fn) cbs[name] = cbs[name] or {}; table.insert(cbs[name], fn) end
function GA:Fire(name, ...)
	local list = cbs[name]; if not list then return end
	for i = 1, #list do
		local ok, err = pcall(list[i], ...)
		if not ok then GA:Print("|cffff5555error|r (" .. name .. "): " .. tostring(err)) end
	end
end

function GA:Print(msg)
	DEFAULT_CHAT_FRAME:AddMessage(GA.COLOR .. "Glen's Auctions:|r " .. tostring(msg))
end

-- ---------------------------------------------------------------- saved data
local DEFAULTS = {
	undercutMode = "copper",   -- "copper" or "percent"
	undercutCopper = 1,
	undercutPercent = 2,
	duration = 2,              -- 1 = 12h, 2 = 24h, 3 = 48h
	replaceBlizzard = true,    -- open our window in place of Blizzard's auction house
	tipMarket = true, tipToday = true, tipSeen = true, tipVendor = true, tipStack = true,
	historyDays = 30,
}

local function fill(t, d)
	for k, v in pairs(d) do if t[k] == nil then t[k] = v end end
end

GA:On("ADDON_LOADED", function(name)
	if name ~= ADDON then return end
	-- WoW Forever sometimes fails to load account-wide saved data, so the same table is also
	-- saved per character; use whichever copy actually came back.
	local db = GlensAuctionsDB
	if type(db) ~= "table" or not db.realms then
		if type(GlensAuctionsBackup) == "table" and GlensAuctionsBackup.realms then
			db = GlensAuctionsBackup
			GA.restoredFromBackup = true
		else
			db = { realms = {} }
		end
	end
	db.settings = db.settings or {}
	fill(db.settings, DEFAULTS)
	db.realms = db.realms or {}
	GlensAuctionsDB = db
	GlensAuctionsBackup = db
	GA.db = db
	GA.set = db.settings
	GA:Fire("Loaded")
end)

GA:On("PLAYER_LOGIN", function()
	local realm = GetRealmName() or "Realm"
	GA.realmKey = realm
	local r = GA.db.realms[realm]
	if not r then
		r = { items = {}, lastFull = 0, ledger = {} }
		GA.db.realms[realm] = r
	end
	r.items = r.items or {}
	r.ledger = r.ledger or {}
	GA.realm = r
	GA:Fire("Ready")
	if GA.restoredFromBackup then
		GA:Print("price data restored from this character's backup copy.")
	end
end)

-- ---------------------------------------------------------------- helpers
-- One key per thing that sells as one thing: the item ID, plus the random suffix ("of the Bear") when there is one.
function GA:KeyFromLink(link)
	if type(link) ~= "string" then return nil end
	local body = link:match("item:([%-%d:]+)")
	if not body then return nil end
	local parts = {}
	for p in (body .. ":"):gmatch("([^:]*):") do parts[#parts + 1] = p end
	local id = tonumber(parts[1])
	if not id then return nil end
	local suffix = tonumber(parts[7] or "") or 0
	if suffix ~= 0 then return id .. ":" .. suffix, id end
	return tostring(id), id
end

function GA:KeyFromID(id) return id and tostring(id) or nil end

function GA:Money(c, short)
	if not c or c <= 0 then return "|cff888888-|r" end
	c = math.floor(c + 0.5)
	if short and c >= 10000 then
		c = math.floor(c / 100) * 100   -- drop the copper on big numbers
	end
	return GetCoinTextureString(c)
end

function GA:Ago(t)
	if not t or t == 0 then return "never" end
	local s = time() - t
	if s < 90 then return "just now" end
	if s < 5400 then return math.floor(s / 60 + 0.5) .. " min ago" end
	if s < 129600 then return math.floor(s / 3600 + 0.5) .. " hours ago" end
	return math.floor(s / 86400 + 0.5) .. " days ago"
end

function GA:ItemInfo(item)
	local getter = (C_Item and C_Item.GetItemInfo) or GetItemInfo
	return getter(item)
end

function GA:VendorPrice(item)
	local sell = select(11, self:ItemInfo(item))
	return sell or 0
end

function GA:Today() return math.floor((time() - 4 * 3600) / 86400) end   -- days roll over at 4am

-- ---------------------------------------------------------------- slash + compartment
SLASH_GLENSAUCTIONS1 = "/ga"
SLASH_GLENSAUCTIONS2 = "/glensauctions"
SlashCmdList.GLENSAUCTIONS = function(msg)
	msg = (msg or ""):lower():match("^%s*(.-)%s*$")
	if msg == "scan" then
		GA:StartScan()
	elseif msg == "show" then
		GA:ShowWindow()
	elseif msg == "blizz" or msg == "blizzard" then
		GA:ShowBlizzard()
	elseif msg == "config" or msg == "settings" then
		GA:ShowWindow("settings")
	else
		GA:Print("v" .. GA.VERSION .. " (build " .. GA.BUILD .. ")")
		GA:Print("/ga scan - full auction house scan (at the auction house)")
		GA:Print("/ga show - Glen's Auctions window,  /ga blizz - Blizzard's auction house")
		GA:Print("/ga settings - settings")
		if GA.realm then
			local n = 0
			for _ in pairs(GA.realm.items) do n = n + 1 end
			GA:Print(("prices known for %d items, last full scan %s"):format(n, GA:Ago(GA.realm.lastFull)))
		end
	end
end

function GlensAuctions_OnCompartmentClick()
	SlashCmdList.GLENSAUCTIONS("")
end
