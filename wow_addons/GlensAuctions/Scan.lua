-- Glen's Auctions - scanning the auction house.
-- Full scan: the modern auction house hands over every listing at once (allowed about every 15 minutes).
-- If that isn't available, falls back to a browse scan (lowest price + quantity per item).
local _, GA = ...

local CAH = C_AuctionHouse
local FULL_COOLDOWN = 15 * 60

GA.scan = nil   -- current scan state

function GA:IsAtAuctionHouse()
	return self.ahOpen and true or false
end

function GA:ScanCooldownLeft()
	local last = self.realm and self.realm.lastFullRequest or 0
	local left = last + FULL_COOLDOWN - time()
	return left > 0 and left or 0
end

local function progress(frac, text)
	GA.scanProgress = frac
	GA.scanText = text
	GA:Fire("ScanProgress", frac, text)
end

local function finish(collected, kind)
	local n = 0
	for key, data in pairs(collected) do
		GA:Record(key, data.prices, data.name)
		n = n + 1
	end
	if kind == "full" then GA.realm.lastFull = time() end
	GA.realm.lastScanKind = kind
	GA.realm.lastScan = time()
	GA.scan = nil
	progress(1, ("Scan complete: %d items priced"):format(n))
	GA:Print(("scan complete - prices updated for %d items."):format(n))
	GA:Fire("ScanDone", n)
end

-- ---------------------------------------------------------------- full (replicate) scan
local function processReplicate()
	local s = GA.scan
	if not s or s.kind ~= "full" then return end
	local total = CAH.GetNumReplicateItems()
	s.total = total
	if total == 0 then
		GA.scan = nil
		progress(0, "The auction house sent nothing back - try again in a moment")
		return
	end
	local i = s.index or 0
	local stop = math.min(total, i + 1500)
	local collected = s.collected
	while i < stop do
		local name, _, count, _, _, _, _, _, _, buyout, _, _, _, _, _, _, itemID = CAH.GetReplicateItemInfo(i)
		if itemID and buyout and buyout > 0 and count and count > 0 then
			local link = CAH.GetReplicateItemLink(i)
			local key = (link and GA:KeyFromLink(link)) or tostring(itemID)
			local c = collected[key]
			if not c then c = { prices = {}, name = name }; collected[key] = c end
			local p = c.prices
			p[#p + 1] = { unit = buyout / count, qty = count }
		end
		i = i + 1
	end
	s.index = i
	progress(i / total, ("Reading listings: %d / %d"):format(i, total))
	if i < total then
		C_Timer.After(0, processReplicate)
	else
		finish(collected, "full")
	end
end

GA:On("REPLICATE_ITEM_LIST_UPDATE", function()
	local s = GA.scan
	if not s or s.kind ~= "full" or s.started then return end
	s.started = true
	-- give the client a moment to finish filling the list
	C_Timer.After(0.5, processReplicate)
end)

-- ---------------------------------------------------------------- browse scan (fallback)
local function readBrowse(results)
	local s = GA.scan
	if not s or s.kind ~= "browse" then return end
	for _, r in ipairs(results or {}) do
		local k = r.itemKey
		if k and r.minPrice and r.minPrice > 0 then
			local key = (k.itemSuffix and k.itemSuffix ~= 0) and (k.itemID .. ":" .. k.itemSuffix) or tostring(k.itemID)
			s.collected[key] = { prices = { { unit = r.minPrice, qty = r.totalQuantity or 1 } } }
			s.count = s.count + 1
		end
	end
	progress(0.5, ("Browsing: %d items so far"):format(s.count))
	if CAH.HasFullBrowseResults() then
		finish(s.collected, "browse")
	else
		CAH.RequestMoreBrowseResults()
	end
end

GA:On("AUCTION_HOUSE_BROWSE_RESULTS_UPDATED", function()
	local s = GA.scan
	if not s or s.kind ~= "browse" then return end
	s.collected, s.count = {}, 0
	readBrowse(CAH.GetBrowseResults())
end)
GA:On("AUCTION_HOUSE_BROWSE_RESULTS_ADDED", function(added)
	readBrowse(added)
end)

-- ---------------------------------------------------------------- start / cancel
function GA:StartScan(forceBrowse)
	if not self:IsAtAuctionHouse() then
		self:Print("open the auction house first.")
		return
	end
	if self.scan then
		self:Print("a scan is already running.")
		return
	end
	local canFull = CAH.ReplicateItems and not forceBrowse
	if canFull and self:ScanCooldownLeft() > 0 then
		local m = math.ceil(self:ScanCooldownLeft() / 60)
		self:Print(("full scans are allowed every 15 minutes - about %d min to go. Doing a quick browse scan instead."):format(m))
		canFull = false
	end
	if canFull then
		self.scan = { kind = "full", collected = {}, index = 0, t0 = time() }
		self.realm.lastFullRequest = time()
		progress(0, "Asking the auction house for everything...")
		CAH.ReplicateItems()
		-- if the server doesn't answer, don't hang forever
		local mine = self.scan
		C_Timer.After(45, function()
			if GA.scan == mine and not mine.started then
				GA.scan = nil
				progress(0, "No answer from the auction house - the full scan is probably on cooldown")
				GA:Print("the auction house didn't answer the full scan (it's probably on its 15 minute cooldown). Try the browse scan, or wait a bit.")
			end
		end)
	else
		self.scan = { kind = "browse", collected = {}, count = 0, t0 = time() }
		progress(0, "Browsing the auction house...")
		CAH.SendBrowseQuery({
			searchString = "",
			sorts = { { sortOrder = Enum.AuctionHouseSortOrder.Price, reverseSort = false } },
			filters = {},
			itemClassFilters = {},
		})
	end
	self:Fire("ScanStarted")
end

function GA:StopScan(reason)
	if not self.scan then return end
	self.scan = nil
	progress(0, reason or "Scan stopped")
end

GA:On("AUCTION_HOUSE_SHOW", function()
	GA.ahOpen = true
	GA:Fire("AHOpen")
end)
GA:On("AUCTION_HOUSE_CLOSED", function()
	GA.ahOpen = false
	if GA.scan and GA.scan.kind == "browse" then GA:StopScan("Auction house closed") end
	GA:Fire("AHClosed")
end)
