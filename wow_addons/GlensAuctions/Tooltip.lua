-- Glen's Auctions - prices on item tooltips (like Auctioneer's tooltip lines).
local _, GA = ...

local function stackCountFor(tooltip)
	-- bag / bank slots: work out how many are in the hovered stack
	local owner = tooltip.GetOwner and tooltip:GetOwner()
	if owner and owner.GetBagID and owner.GetID then
		local ok, bag = pcall(owner.GetBagID, owner)
		if ok and bag and C_Container and C_Container.GetContainerItemInfo then
			local info = C_Container.GetContainerItemInfo(bag, owner:GetID())
			if info and info.stackCount then return info.stackCount end
		end
	end
	return 1
end

local function addLines(tooltip, link)
	if not GA.set or not link or tooltip.gaDone == link then return end
	tooltip.gaDone = link
	local set = GA.set
	local market, todayLow, days, avgQty, newest = GA:MarketForLink(link)
	local vendor = GA:VendorPrice(link)
	local count = set.tipStack and stackCountFor(tooltip) or 1
	if not market and (not vendor or vendor == 0) then return end

	tooltip:AddLine(GA.COLOR .. "Glen's Auctions|r" .. (count > 1 and ("  |cffaaaaaa(x" .. count .. ")|r") or ""))
	if market then
		if set.tipMarket then
			local label = days and days > 0 and "  Market value" or "  Market value |cffaa8844(old)|r"
			if count > 1 then
				tooltip:AddDoubleLine(label, GA:Money(market * count, true) .. " |cffaaaaaa(" .. GA:Money(market, true) .. " each)|r", 1, 0.82, 0, 1, 1, 1)
			else
				tooltip:AddDoubleLine(label, GA:Money(market), 1, 0.82, 0, 1, 1, 1)
			end
		end
		if set.tipToday and todayLow then
			tooltip:AddDoubleLine("  Lowest today", GA:Money(todayLow), 0.8, 0.8, 0.8, 1, 1, 1)
		end
		if set.tipSeen and days and days > 0 then
			tooltip:AddDoubleLine("  Seen", ("%d day%s, ~%d on sale"):format(days, days == 1 and "" or "s", avgQty or 0), 0.8, 0.8, 0.8, 0.8, 0.8, 0.8)
		end
	else
		tooltip:AddLine("  |cff888888Never seen at auction|r")
	end
	if set.tipVendor and vendor and vendor > 0 then
		local txt = count > 1 and (GA:Money(vendor * count) .. " |cffaaaaaa(" .. GA:Money(vendor) .. " each)|r") or GA:Money(vendor)
		tooltip:AddDoubleLine("  Vendor buys for", txt, 0.8, 0.8, 0.8, 1, 1, 1)
	end
	if GA.LedgerTooltip then GA:LedgerTooltip(tooltip, link) end
	tooltip:Show()
end

local function clear(tooltip) tooltip.gaDone = nil end

local function hook()
	if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum.TooltipDataType then
		TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(tooltip, data)
			if not tooltip or not tooltip.GetItem then return end
			local _, link = tooltip:GetItem()
			if not link and data and data.hyperlink then link = data.hyperlink end
			addLines(tooltip, link)
		end)
	else
		for _, tt in ipairs({ GameTooltip, ItemRefTooltip, ShoppingTooltip1, ShoppingTooltip2 }) do
			if tt and tt.HookScript then
				tt:HookScript("OnTooltipSetItem", function(self)
					local _, link = self:GetItem()
					addLines(self, link)
				end)
			end
		end
	end
	for _, tt in ipairs({ GameTooltip, ItemRefTooltip, ShoppingTooltip1, ShoppingTooltip2 }) do
		if tt and tt.HookScript then tt:HookScript("OnTooltipCleared", clear) end
	end
end

GA:Listen("Loaded", hook)
