-- Glen's Auctions - settings tab.
local _, GA = ...

local function check(parent, label, key, y, onChange)
	local cb = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
	cb:SetSize(24, 24)
	cb:SetPoint("TOPLEFT", 12, y)
	local t = GA:Text(cb, "normal", "LEFT", { 1, 1, 1 })
	t:SetPoint("LEFT", cb, "RIGHT", 4, 0)
	t:SetText(label)
	cb:SetScript("OnShow", function(self) self:SetChecked(GA.set[key] and true or false) end)
	cb:SetScript("OnClick", function(self)
		GA.set[key] = self:GetChecked() and true or false
		if onChange then onChange() end
	end)
	return cb
end

local function number(parent, label, key, x, y, w)
	local t = GA:Text(parent, "normal", "LEFT", { 1, 1, 1 })
	t:SetPoint("TOPLEFT", x, y)
	t:SetText(label)
	local eb = CreateFrame("EditBox", nil, parent, "InputBoxTemplate")
	eb:SetSize(w or 50, 20)
	eb:SetPoint("LEFT", t, "RIGHT", 10, 0)
	eb:SetAutoFocus(false)
	eb:SetNumeric(true)
	eb:SetScript("OnShow", function(self) self:SetText(tostring(GA.set[key] or 0)) end)
	eb:SetScript("OnTextChanged", function(self, user)
		if user then GA.set[key] = tonumber(self:GetText()) or 0 end
	end)
	eb:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
	return eb
end

GA:Listen("WindowBuilt", function()
	local p = GA.panels.settings
	local box = GA:Inset(p)
	box:SetAllPoints()

	local h1 = GA:Text(box, "big", "LEFT"); h1:SetPoint("TOPLEFT", 14, -12); h1:SetText("Auction house")
	check(box, "Open Glen's Auctions instead of Blizzard's auction house", "replaceBlizzard", -36)

	local h2 = GA:Text(box, "big", "LEFT"); h2:SetPoint("TOPLEFT", 14, -72); h2:SetText("Undercutting")
	local modes = {}
	local function setMode(m)
		GA.set.undercutMode = m
		modes.copper:SetChecked(m == "copper"); modes.percent:SetChecked(m == "percent")
	end
	modes.copper = CreateFrame("CheckButton", nil, box, "UICheckButtonTemplate")
	modes.copper:SetSize(24, 24); modes.copper:SetPoint("TOPLEFT", 12, -96)
	modes.copper:SetScript("OnClick", function() setMode("copper") end)
	number(box, "Undercut by this many copper:", "undercutCopper", 44, -100, 60)
	modes.percent = CreateFrame("CheckButton", nil, box, "UICheckButtonTemplate")
	modes.percent:SetSize(24, 24); modes.percent:SetPoint("TOPLEFT", 12, -124)
	modes.percent:SetScript("OnClick", function() setMode("percent") end)
	number(box, "Undercut by this percent:", "undercutPercent", 44, -128, 40)
	box:SetScript("OnShow", function() setMode(GA.set.undercutMode or "copper") end)

	local h3 = GA:Text(box, "big", "LEFT"); h3:SetPoint("TOPLEFT", 14, -164); h3:SetText("Tooltips")
	check(box, "Market value", "tipMarket", -188)
	check(box, "Lowest price seen today", "tipToday", -212)
	check(box, "How often it's been seen", "tipSeen", -236)
	check(box, "Vendor price", "tipVendor", -260)
	check(box, "Whole-stack prices when hovering a stack", "tipStack", -284)

	local h4 = GA:Text(box, "big", "LEFT"); h4:SetPoint("TOPLEFT", 420, -12); h4:SetText("Price history")
	number(box, "Keep this many days:", "historyDays", 420, -40, 40)
	local note = GA:Text(box, "small", "LEFT", { 0.75, 0.75, 0.75 })
	note:SetPoint("TOPLEFT", 420, -70)
	note:SetWidth(340)
	note:SetJustifyV("TOP")
	note:SetText("Market value blends the last 14 days of scans, newer days counting more, and ignores the odd silly listing.\n\nFull scans are allowed about every 15 minutes by the game. Shift-click Scan for a quick browse scan (lowest prices only) any time.\n\n/ga - status    /ga scan - scan    /ga blizz - Blizzard's auction house")
end)
