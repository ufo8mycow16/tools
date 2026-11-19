-- Glen's Auctions - Appraiser: the classic Auctioneer posting tab, rebuilt for the modern auction house.
-- Left: everything in your bags you can sell. Right: what's on the auction house now, a suggested
-- (undercut) price, and the posting controls.
local _, GA = ...

local CAH = C_AuctionHouse
local apr = { items = {}, listings = {} }
GA.apr = apr

local DUR_TEXT = { "12 hours", "24 hours", "48 hours" }
local TIMELEFT_TEXT = { [0] = "< 30 min", [1] = "30m - 2h", [2] = "2 - 12h", [3] = "12 - 48h" }

-- ---------------------------------------------------------------- money input (gold / silver / copper boxes)
function GA:MoneyInput(parent, onChange)
	local f = CreateFrame("Frame", nil, parent)
	f:SetSize(170, 22)
	local boxes = {}
	local coins = { "Interface\\MoneyFrame\\UI-GoldIcon", "Interface\\MoneyFrame\\UI-SilverIcon", "Interface\\MoneyFrame\\UI-CopperIcon" }
	local widths = { 62, 30, 30 }
	local x = 0
	for i = 1, 3 do
		local eb = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
		eb:SetSize(widths[i], 20)
		eb:SetPoint("LEFT", x + 6, 0)
		eb:SetAutoFocus(false)
		eb:SetNumeric(true)
		eb:SetMaxLetters(i == 1 and 7 or 2)
		eb:SetJustifyH("RIGHT")
		eb:SetScript("OnTextChanged", function(_, user) if user and onChange then onChange(f:Get()) end end)
		eb:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
		eb:SetScript("OnTabPressed", function(self) local n = boxes[i % 3 + 1]; n:SetFocus() end)
		local icon = f:CreateTexture(nil, "ARTWORK")
		icon:SetSize(13, 13)
		icon:SetTexture(coins[i])
		icon:SetPoint("LEFT", eb, "RIGHT", 2, 0)
		boxes[i] = eb
		x = x + widths[i] + 22
	end
	f:SetWidth(x)
	function f:Get()
		local g, s, c = tonumber(boxes[1]:GetText()) or 0, tonumber(boxes[2]:GetText()) or 0, tonumber(boxes[3]:GetText()) or 0
		return g * 10000 + s * 100 + c
	end
	function f:Set(copper)
		copper = math.max(0, math.floor((copper or 0) + 0.5))
		boxes[1]:SetText(tostring(math.floor(copper / 10000)))
		boxes[2]:SetText(tostring(math.floor(copper / 100) % 100))
		boxes[3]:SetText(tostring(copper % 100))
	end
	function f:SetEnabled(on)
		for i = 1, 3 do boxes[i]:SetEnabled(on); boxes[i]:SetAlpha(on and 1 or 0.4) end
	end
	return f
end

-- ---------------------------------------------------------------- reading the bags
local function isCommodity(loc)
	if CAH.GetItemCommodityStatus and Enum.ItemCommodityStatus then
		local st = CAH.GetItemCommodityStatus(loc)
		if st == Enum.ItemCommodityStatus.Commodity then return true end
		if st == Enum.ItemCommodityStatus.Item then return false end
	end
	return nil  -- unknown (item data not loaded yet)
end

function apr:ReadBags()
	local byKey, list = {}, {}
	local lastBag = (Enum.BagIndex and Enum.BagIndex.ReagentBag) or 4
	for bag = 0, lastBag do
		local slots = C_Container.GetContainerNumSlots(bag) or 0
		for slot = 1, slots do
			local info = C_Container.GetContainerItemInfo(bag, slot)
			if info and info.hyperlink and not info.isBound then
				local loc = ItemLocation:CreateFromBagAndSlot(bag, slot)
				local ok = true
				if GA.ahOpen and CAH.IsSellItemValid then ok = CAH.IsSellItemValid(loc, false) end
				if ok then
					local commodity = isCommodity(loc)
					local key = GA:KeyFromLink(info.hyperlink)
					-- gear with different item levels/enchants shouldn't be lumped together
					local groupKey = commodity and key or info.hyperlink
					local e = byKey[groupKey]
					if not e then
						e = { key = key, link = info.hyperlink, itemID = info.itemID, icon = info.iconFileID,
							quality = info.quality, count = 0, loc = loc, commodity = commodity }
						byKey[groupKey] = e
						list[#list + 1] = e
					end
					e.count = e.count + (info.stackCount or 1)
				end
			end
		end
	end
	for _, e in ipairs(list) do
		e.name = GA:ItemInfo(e.link) or e.link:match("%[(.-)%]") or "?"
		e.market = GA:MarketForLink(e.link)
	end
	table.sort(list, function(a, b)
		local va, vb = (a.market or 0) * a.count, (b.market or 0) * b.count
		if va ~= vb then return va > vb end
		return a.name < b.name
	end)
	self.items = list
	return list
end

-- ---------------------------------------------------------------- talking to the auction house
local SORT = { { sortOrder = Enum.AuctionHouseSortOrder and Enum.AuctionHouseSortOrder.Price or 0, reverseSort = false } }

function apr:Query(e)
	if not GA.ahOpen or not e then return end
	local itemKey
	if e.commodity then
		itemKey = CAH.MakeItemKey(e.itemID)
	else
		itemKey = CAH.GetItemKeyFromItem(e.loc)
	end
	if not itemKey then return end
	self.pendingKey = itemKey
	self.listings = {}
	self.status = "Searching..."
	self:Refresh()
	if CAH.IsThrottledMessageSystemReady and not CAH.IsThrottledMessageSystemReady() then
		self.waitingThrottle = true
		return
	end
	self:Send()
end

function apr:Send()
	local k = self.pendingKey
	if not k then return end
	self.waitingThrottle = false
	local fn = CAH.SendSellSearchQuery or CAH.SendSearchQuery
	fn(k, SORT, true)
end

GA:On("AUCTION_HOUSE_THROTTLED_SYSTEM_READY", function()
	if apr.waitingThrottle then apr:Send() end
end)

local function readCommodity(itemID)
	local sel = apr.sel
	if not sel or not sel.commodity or sel.itemID ~= itemID then return end
	local out, prices = {}, {}
	for i = 1, CAH.GetNumCommoditySearchResults(itemID) do
		local r = CAH.GetCommoditySearchResultInfo(itemID, i)
		if r then
			local mine = (r.numOwnerItems or 0) > 0 or r.containsOwnerItem
			out[#out + 1] = { unit = r.unitPrice, qty = r.quantity, left = r.timeLeftSeconds, mine = mine,
				seller = mine and "You" or ((r.owners and r.owners[1]) or "") }
			prices[#prices + 1] = { unit = r.unitPrice, qty = r.quantity }
		end
	end
	if CAH.HasFullCommoditySearchResults and not CAH.HasFullCommoditySearchResults(itemID) and #out < 500 then
		CAH.RequestMoreCommoditySearchResults(itemID)
	end
	GA:Record(sel.key, prices, sel.name)
	apr.listings = out
	apr.status = #out == 0 and "Nobody is selling this right now" or nil
	apr:Suggest()
	apr:Refresh()
end

local function readItems(itemKey)
	local sel = apr.sel
	if not sel or sel.commodity or not itemKey or itemKey.itemID ~= sel.itemID then return end
	local out, prices = {}, {}
	for i = 1, CAH.GetNumItemSearchResults(itemKey) do
		local r = CAH.GetItemSearchResultInfo(itemKey, i)
		if r then
			local qty = r.quantity or 1
			local each = r.buyoutAmount and (r.buyoutAmount / qty) or nil
			local mine = r.containsOwnerItem
			out[#out + 1] = { unit = each, bid = r.bidAmount or r.minBid, qty = qty, band = r.timeLeft, mine = mine,
				seller = mine and "You" or ((r.owners and r.owners[1]) or ""), link = r.itemLink }
			if each then prices[#prices + 1] = { unit = each, qty = qty } end
		end
	end
	if CAH.HasFullItemSearchResults and not CAH.HasFullItemSearchResults(itemKey) and #out < 500 then
		CAH.RequestMoreItemSearchResults(itemKey)
	end
	GA:Record(sel.key, prices, sel.name)
	table.sort(out, function(a, b) return (a.unit or 1e15) < (b.unit or 1e15) end)
	apr.listings = out
	apr.status = #out == 0 and "Nobody is selling this right now" or nil
	apr:Suggest()
	apr:Refresh()
end

GA:On("COMMODITY_SEARCH_RESULTS_UPDATED", readCommodity)
GA:On("COMMODITY_SEARCH_RESULTS_ADDED", readCommodity)
GA:On("ITEM_SEARCH_RESULTS_UPDATED", readItems)
GA:On("ITEM_SEARCH_RESULTS_ADDED", readItems)

-- ---------------------------------------------------------------- price suggestion
function apr:Undercut(price)
	local set = GA.set
	if set.undercutMode == "percent" then
		return math.max(1, math.floor(price * (1 - (set.undercutPercent or 0) / 100)))
	end
	return math.max(1, price - (set.undercutCopper or 1))
end

function apr:Suggest()
	local sel = self.sel
	if not sel or not self.ui then return end
	local cheapest
	for _, l in ipairs(self.listings) do
		if l.unit and l.unit > 0 then cheapest = l; break end
	end
	local price, why
	if cheapest then
		if cheapest.mine then
			price, why = cheapest.unit, "matching your own cheapest listing"
		else
			price, why = self:Undercut(cheapest.unit), "undercutting the cheapest listing"
		end
	elseif sel.market then
		price, why = sel.market, "market value (nobody else is selling)"
	else
		local v = GA:VendorPrice(sel.link)
		if v > 0 then price, why = v * 3, "3x vendor price (no auction data)" end
	end
	self.suggested, self.why = price, why
	if price and not self.userPrice then self.ui.price:Set(price) end
	self:UpdateTotals()
end

-- ---------------------------------------------------------------- posting
local pendingPost

function apr:Post()
	local sel = self.sel
	if not sel or not GA.ahOpen then return end
	local q = tonumber(self.ui.qty:GetText()) or 0
	if q < 1 then GA:Print("enter how many to post."); return end
	if q > sel.count then q = sel.count end
	local unit = self.ui.price:Get()
	if unit < 1 then GA:Print("set a price first."); return end
	local d = GA.set.duration or 2
	if not C_Item.DoesItemExist(sel.loc) then
		GA:Print("that item has moved in your bags - pick it again.")
		self:Rebuild(); return
	end
	if sel.commodity then
		pendingPost = { "commodity", sel.loc, d, q, unit }
		CAH.PostCommodity(sel.loc, d, q, unit)
	else
		local bid = self.ui.bid:Get()
		if bid <= 0 or bid >= unit then bid = nil end
		pendingPost = { "item", sel.loc, d, q, bid, unit }
		CAH.PostItem(sel.loc, d, q, bid, unit)
	end
	self.userPrice = nil
end

StaticPopupDialogs["GLENSAUCTIONS_POST_WARNING"] = {
	text = "The auction house thinks this price looks unusual.\nPost it anyway?",
	button1 = YES or "Yes",
	button2 = NO or "No",
	OnAccept = function()
		local p = pendingPost
		if not p then return end
		if p[1] == "commodity" and CAH.ConfirmPostCommodity then
			CAH.ConfirmPostCommodity(p[2], p[3], p[4], p[5])
		elseif p[1] == "item" and CAH.ConfirmPostItem then
			CAH.ConfirmPostItem(p[2], p[3], p[4], p[5], p[6])
		end
	end,
	timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
}
GA:On("AUCTION_HOUSE_POST_WARNING", function() StaticPopup_Show("GLENSAUCTIONS_POST_WARNING") end)

GA:On("AUCTION_HOUSE_AUCTION_CREATED", function()
	local p = pendingPost
	pendingPost = nil
	if p and apr.sel then
		local each = p[1] == "commodity" and p[5] or p[6]
		GA:Print(("posted %d x %s at %s each."):format(p[4], apr.sel.link, GA:Money(each)))
		if GA.LedgerPosted then GA:LedgerPosted(apr.sel, p[4], each) end
	end
	C_Timer.After(0.6, function()
		apr:Rebuild()
		if apr.sel then apr:Query(apr.sel) end
	end)
end)

-- ---------------------------------------------------------------- the panel
function apr:UpdateTotals()
	local ui, sel = self.ui, self.sel
	if not ui or not sel then return end
	local q = tonumber(ui.qty:GetText()) or 0
	local unit = ui.price:Get()
	local d = GA.set.duration or 2
	local deposit
	if GA.ahOpen and q > 0 and C_Item.DoesItemExist(sel.loc) then
		if sel.commodity and CAH.CalculateCommodityDeposit then
			deposit = CAH.CalculateCommodityDeposit(sel.itemID, d, q)
		elseif CAH.CalculateItemDeposit then
			deposit = CAH.CalculateItemDeposit(sel.loc, d, q)
		end
	end
	local vendor = GA:VendorPrice(sel.link)
	local warn = (vendor > 0 and unit > 0 and unit < vendor) and "  |cffff4444(below vendor price!)|r" or ""
	ui.totals:SetText(("Total: %s     Deposit: %s%s"):format(GA:Money(unit * q), deposit and GA:Money(deposit) or "-", warn))
	ui.why:SetText(self.why and ("|cffaaaaaaSuggested: " .. self.why .. "|r") or "")
end

function apr:Select(e)
	self.sel = e
	self.userPrice = nil
	self.listings = {}
	local ui = self.ui
	if not e then
		ui.header:Hide(); ui.post:Hide()
		self:Refresh(); return
	end
	ui.header:Show(); ui.post:Show()
	ui.icon:SetTexture(e.icon)
	local r, g, b = 1, 1, 1
	if e.quality and C_Item and C_Item.GetItemQualityColor then r, g, b = C_Item.GetItemQualityColor(e.quality) end
	ui.name:SetText(e.name)
	ui.name:SetTextColor(r, g, b)
	local market, todayLow, days = GA:MarketForLink(e.link)
	local vendor = GA:VendorPrice(e.link)
	ui.info:SetText(("Market: %s     Lowest today: %s     Vendor: %s     Seen: %s"):format(
		GA:Money(market), GA:Money(todayLow), GA:Money(vendor), days and (days .. " days") or "never"))
	ui.qty:SetText(tostring(e.commodity and e.count or 1))
	ui.qtyMax:SetText("of " .. e.count)
	ui.bid:SetEnabled(not e.commodity)
	ui.bid:Set(0)
	ui.price:Set(0)
	self:Suggest()
	self:Query(e)
	self:Refresh()
end

function apr:Refresh()
	local ui = self.ui
	if not ui then return end
	-- left list
	local rows = {}
	for _, e in ipairs(self.items) do
		rows[#rows + 1] = { data = e, icon = e.icon, link = e.link,
			cells = { e.name, tostring(e.count), e.market and GA:Money(e.market * e.count, true) or "|cff888888-|r" } }
	end
	ui.itemList.selected = self.sel
	ui.itemList:SetData(rows)
	ui.empty:SetShown(#rows == 0)
	-- listings
	local lrows = {}
	for _, l in ipairs(self.listings) do
		local left = l.left and (l.left < 1800 and "< 30 min" or (l.left < 7200 and "30m - 2h" or (l.left < 43200 and "2 - 12h" or "12 - 48h"))) or TIMELEFT_TEXT[l.band or -1] or ""
		lrows[#lrows + 1] = { data = l, link = l.link,
			cells = { l.unit and GA:Money(l.unit) or "|cff888888bid only|r", tostring(l.qty), left, l.seller or "" },
			color = l.mine and { 0.4, 1, 0.4 } or nil }
	end
	ui.listings:SetData(lrows)
	ui.listStatus:SetText(self.status or (#lrows > 0 and (#lrows .. " listings") or ""))
end

function apr:Rebuild()
	local keepKey = self.sel and (self.sel.commodity and self.sel.key or self.sel.link)
	self:ReadBags()
	local found
	if keepKey then
		for _, e in ipairs(self.items) do
			if (e.commodity and e.key or e.link) == keepKey then found = e; break end
		end
	end
	self.sel = found
	if found and self.ui then
		self.ui.qtyMax:SetText("of " .. found.count)
	elseif self.ui then
		self:Select(nil)
	end
	self:Refresh()
end

local function buildPanel(panel)
	local ui = {}
	apr.ui = ui

	-- left: your items
	local left = GA:Inset(panel)
	left:SetPoint("TOPLEFT", 0, 0)
	left:SetPoint("BOTTOMLEFT", 0, 0)
	left:SetWidth(270)
	local lt = GA:Text(left, "normal", "LEFT"); lt:SetPoint("TOPLEFT", 8, -7); lt:SetText("Your items")
	local lsub = GA:Text(left, "small", "RIGHT", { 0.7, 0.7, 0.7 }); lsub:SetPoint("TOPRIGHT", -10, -9); lsub:SetText("market value")
	ui.itemList = GA:List(left, 20, { icon = true, { width = 132 }, { width = 30, justify = "RIGHT" }, { justify = "RIGHT" } },
		function(e) apr:Select(e) end)
	ui.itemList:SetPoint("TOPLEFT", 6, -26)
	ui.itemList:SetPoint("BOTTOMRIGHT", -6, 6)
	ui.empty = GA:Text(left, "small", "CENTER", { 0.7, 0.7, 0.7 })
	ui.empty:SetPoint("CENTER")
	ui.empty:SetText("Nothing in your bags\nthat can be auctioned.")

	-- right top: item header
	local header = CreateFrame("Frame", nil, panel)
	header:SetPoint("TOPLEFT", left, "TOPRIGHT", 10, 0)
	header:SetPoint("TOPRIGHT", 0, 0)
	header:SetHeight(44)
	ui.header = header
	ui.icon = header:CreateTexture(nil, "ARTWORK")
	ui.icon:SetSize(38, 38); ui.icon:SetPoint("TOPLEFT", 2, -2)
	ui.name = GA:Text(header, "big", "LEFT"); ui.name:SetPoint("TOPLEFT", ui.icon, "TOPRIGHT", 8, -1)
	ui.info = GA:Text(header, "small", "LEFT", { 0.9, 0.9, 0.9 }); ui.info:SetPoint("BOTTOMLEFT", ui.icon, "BOTTOMRIGHT", 8, 2)
	header:Hide()

	-- right middle: current listings
	local mid = GA:Inset(panel)
	mid:SetPoint("TOPLEFT", left, "TOPRIGHT", 10, -48)
	mid:SetPoint("TOPRIGHT", 0, -48)
	mid:SetHeight(150)
	local cols = { "Price each", "Qty", "Time left", "Seller" }
	local cw = { 150, 50, 80 }
	local x = 10
	for i, c in ipairs(cols) do
		local h = GA:Text(mid, "small", "LEFT", { 1, 0.82, 0 })
		h:SetPoint("TOPLEFT", x, -6); h:SetText(c)
		x = x + (cw[i] or 0) + 4
	end
	ui.listStatus = GA:Text(mid, "small", "RIGHT", { 0.7, 0.7, 0.7 }); ui.listStatus:SetPoint("TOPRIGHT", -40, -6)
	local refresh = GA:Button(mid, "R", 22, 18, function() if apr.sel then apr:Query(apr.sel) end end)
	refresh:SetPoint("TOPRIGHT", -8, -3)
	ui.listings = GA:List(mid, 16, { { width = 150, justify = "LEFT" }, { width = 50, justify = "LEFT" }, { width = 80 }, {} },
		function(l)
			if l and l.unit then
				apr.userPrice = true
				ui.price:Set(l.mine and l.unit or apr:Undercut(l.unit))
				apr.why = l.mine and "matching your listing" or "undercutting the listing you clicked"
				apr:UpdateTotals()
			end
		end)
	ui.listings:SetPoint("TOPLEFT", 8, -22)
	ui.listings:SetPoint("BOTTOMRIGHT", -6, 6)

	-- right bottom: posting
	local post = GA:Inset(panel)
	post:SetPoint("TOPLEFT", mid, "BOTTOMLEFT", 0, -6)
	post:SetPoint("BOTTOMRIGHT", 0, 0)
	ui.post = post
	post:Hide()

	local l1 = GA:Text(post, "normal", "LEFT"); l1:SetPoint("TOPLEFT", 12, -14); l1:SetText("Quantity")
	ui.qty = CreateFrame("EditBox", nil, post, "InputBoxTemplate")
	ui.qty:SetSize(50, 20); ui.qty:SetPoint("LEFT", l1, "RIGHT", 12, 0)
	ui.qty:SetAutoFocus(false); ui.qty:SetNumeric(true); ui.qty:SetMaxLetters(5)
	ui.qty:SetScript("OnTextChanged", function() apr:UpdateTotals() end)
	ui.qty:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
	ui.qtyMax = GA:Text(post, "small", "LEFT", { 0.8, 0.8, 0.8 }); ui.qtyMax:SetPoint("LEFT", ui.qty, "RIGHT", 6, 0)
	local all = GA:Button(post, "All", 40, 20, function() if apr.sel then ui.qty:SetText(tostring(apr.sel.count)) end end)
	all:SetPoint("LEFT", ui.qtyMax, "RIGHT", 6, 0)

	local l2 = GA:Text(post, "normal", "LEFT"); l2:SetPoint("TOPLEFT", 12, -44); l2:SetText("Buyout each")
	ui.price = GA:MoneyInput(post, function() apr.userPrice = true; apr.why = "your price"; apr:UpdateTotals() end)
	ui.price:SetPoint("LEFT", l2, "RIGHT", 6, 0)

	local l3 = GA:Text(post, "normal", "LEFT"); l3:SetPoint("TOPLEFT", 12, -72); l3:SetText("Starting bid")
	ui.bid = GA:MoneyInput(post, function() apr:UpdateTotals() end)
	ui.bid:SetPoint("LEFT", l3, "RIGHT", 6, 0)
	local bidNote = GA:Text(post, "small", "LEFT", { 0.6, 0.6, 0.6 }); bidNote:SetPoint("LEFT", ui.bid, "RIGHT", 6, 0)
	bidNote:SetText("(gear only, optional)")

	-- duration
	ui.dur = {}
	local dl = GA:Text(post, "normal", "LEFT"); dl:SetPoint("TOPLEFT", 330, -14); dl:SetText("Duration")
	for i = 1, 3 do
		local cb = CreateFrame("CheckButton", nil, post, "UICheckButtonTemplate")
		cb:SetSize(22, 22)
		cb:SetPoint("TOPLEFT", 326 + (i - 1) * 62, -32)
		local t = GA:Text(cb, "small", "LEFT"); t:SetPoint("LEFT", cb, "RIGHT", 0, 0); t:SetText((DUR_TEXT[i]:gsub(" hours", "h")))
		cb:SetScript("OnClick", function()
			GA.set.duration = i
			for j = 1, 3 do ui.dur[j]:SetChecked(j == i) end
			apr:UpdateTotals()
		end)
		ui.dur[i] = cb
	end

	local undercut = GA:Button(post, "Undercut", 80, 22, function() apr.userPrice = nil; apr:Suggest() end)
	undercut:SetPoint("TOPLEFT", 330, -66)
	local mkt = GA:Button(post, "Market", 70, 22, function()
		if apr.sel then
			local m = GA:MarketForLink(apr.sel.link)
			if m then apr.userPrice = true; ui.price:Set(m); apr.why = "market value"; apr:UpdateTotals() end
		end
	end)
	mkt:SetPoint("LEFT", undercut, "RIGHT", 4, 0)

	ui.why = GA:Text(post, "small", "LEFT"); ui.why:SetPoint("BOTTOMLEFT", 12, 32)
	ui.totals = GA:Text(post, "normal", "LEFT", { 1, 1, 1 }); ui.totals:SetPoint("BOTTOMLEFT", 12, 12)
	local postBtn = GA:Button(post, "Post", 100, 26, function() apr:Post() end)
	postBtn:SetPoint("BOTTOMRIGHT", -10, 8)
	ui.postBtn = postBtn

	panel:SetScript("OnShow", function()
		for j = 1, 3 do ui.dur[j]:SetChecked(j == (GA.set.duration or 2)) end
		apr:Rebuild()
	end)
end

GA:Listen("WindowBuilt", function() buildPanel(GA.panels.appraiser) end)

GA:On("BAG_UPDATE_DELAYED", function()
	if apr.ui and GA.panels.appraiser and GA.panels.appraiser:IsVisible() then apr:Rebuild() end
end)
GA:Listen("ScanDone", function()
	if apr.ui and GA.panels.appraiser:IsVisible() then apr:Rebuild() end
end)
