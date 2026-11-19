-- Glen's Auctions - the main window, in the classic Auctioneer style (original Auctioneer artwork),
-- shown in place of Blizzard's auction house. Tabs at the bottom, scan bar along the top.
local _, GA = ...

local TEX = GA.TEX
local W, H = 832, 447
local main
GA.panels = {}
GA.tabs = {}

-- ---------------------------------------------------------------- small widget helpers
function GA:Inset(parent)
	local f = CreateFrame("Frame", nil, parent, "BackdropTemplate")
	f:SetBackdrop({
		bgFile = TEX .. "BlackBack", tile = true, tileSize = 8,
		edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", edgeSize = 12,
		insets = { left = 3, right = 3, top = 3, bottom = 3 },
	})
	f:SetBackdropColor(0, 0, 0, 0.55)
	f:SetBackdropBorderColor(0.6, 0.55, 0.35, 0.9)
	return f
end

function GA:Text(parent, size, justify, color)
	local fs = parent:CreateFontString(nil, "OVERLAY", size == "small" and "GameFontNormalSmall" or (size == "big" and "GameFontNormalLarge" or "GameFontNormal"))
	fs:SetJustifyH(justify or "LEFT")
	if color then fs:SetTextColor(color[1], color[2], color[3]) end
	return fs
end

function GA:Button(parent, text, w, h, onClick)
	local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
	b:SetSize(w or 100, h or 22)
	b:SetText(text)
	if onClick then b:SetScript("OnClick", onClick) end
	return b
end

-- A simple scrolling list. columns = { {width=, justify=}, ... }; rows are { cells = {...}, icon=, data=, color= }
function GA:List(parent, rowH, columns, onSelect)
	local list = CreateFrame("Frame", nil, parent)
	list.rowH, list.columns, list.onSelect = rowH, columns, onSelect
	list.rows, list.data, list.offset = {}, {}, 0
	list:EnableMouseWheel(true)

	local bar = CreateFrame("Slider", nil, list)
	bar:SetOrientation("VERTICAL")
	bar:SetWidth(12)
	bar:SetPoint("TOPRIGHT", 0, 0)
	bar:SetPoint("BOTTOMRIGHT", 0, 0)
	bar:SetThumbTexture("Interface\\Buttons\\UI-ScrollBar-Knob")
	local bg = bar:CreateTexture(nil, "BACKGROUND")
	bg:SetAllPoints(); bg:SetColorTexture(0, 0, 0, 0.35)
	bar:SetMinMaxValues(0, 0); bar:SetValueStep(1); bar:SetObeyStepOnDrag(true)
	bar:SetScript("OnValueChanged", function(_, v) list.offset = math.floor(v + 0.5); list:Redraw() end)
	list.bar = bar
	list:SetScript("OnMouseWheel", function(_, delta)
		bar:SetValue(math.max(0, math.min(select(2, bar:GetMinMaxValues()), list.offset - delta * 3)))
	end)

	function list:Build()
		local n = math.max(1, math.floor(self:GetHeight() / self.rowH))
		for i = #self.rows + 1, n do
			local r = CreateFrame("Button", nil, self)
			r:SetHeight(self.rowH)
			r:SetPoint("TOPLEFT", 0, -(i - 1) * self.rowH)
			r:SetPoint("TOPRIGHT", -14, -(i - 1) * self.rowH)
			r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
			local sel = r:CreateTexture(nil, "BACKGROUND")
			sel:SetAllPoints(); sel:SetColorTexture(1, 0.82, 0, 0.18); sel:Hide()
			r.sel = sel
			local x = 2
			if self.columns.icon then
				r.icon = r:CreateTexture(nil, "ARTWORK")
				r.icon:SetSize(self.rowH - 2, self.rowH - 2)
				r.icon:SetPoint("LEFT", 1, 0)
				x = self.rowH + 2
			end
			r.cells = {}
			for c, col in ipairs(self.columns) do
				local fs = r:CreateFontString(nil, "OVERLAY", col.font or "GameFontHighlightSmall")
				fs:SetJustifyH(col.justify or "LEFT")
				fs:SetWordWrap(false)
				if col.width then
					fs:SetWidth(col.width); fs:SetPoint("LEFT", x, 0); x = x + col.width + 4
				else
					fs:SetPoint("LEFT", x, 0); fs:SetPoint("RIGHT", -2, 0)
				end
				r.cells[c] = fs
			end
			r:SetScript("OnClick", function(btn)
				if btn.row then
					self.selected = btn.row.data
					self:Redraw()
					if self.onSelect then self.onSelect(btn.row.data, btn.row) end
				end
			end)
			r:SetScript("OnEnter", function(btn)
				if btn.row and btn.row.link then
					GameTooltip:SetOwner(btn, "ANCHOR_RIGHT")
					GameTooltip:SetHyperlink(btn.row.link)
					GameTooltip:Show()
				end
			end)
			r:SetScript("OnLeave", function() GameTooltip:Hide() end)
			self.rows[i] = r
		end
		self.visible = n
	end

	function list:SetData(data)
		self.data = data or {}
		if not self.visible then self:Build() end
		local max = math.max(0, #self.data - self.visible)
		self.bar:SetMinMaxValues(0, max)
		if self.offset > max then self.offset = max end
		self.bar:SetValue(self.offset)
		self.bar:SetShown(max > 0)
		self:Redraw()
	end

	function list:Redraw()
		if not self.visible then self:Build() end
		for i = 1, #self.rows do
			local r = self.rows[i]
			local row = (i <= self.visible) and self.data[i + self.offset] or nil
			r.row = row
			if row then
				for c, fs in ipairs(r.cells) do
					fs:SetText(row.cells[c] or "")
					local col = row.colors and row.colors[c] or row.color
					if col then fs:SetTextColor(col[1], col[2], col[3]) else fs:SetTextColor(1, 1, 1) end
				end
				if r.icon then r.icon:SetTexture(row.icon); r.icon:Show() end
				r.sel:SetShown(self.selected ~= nil and row.data == self.selected)
				r:Show()
			else
				r:Hide()
			end
		end
	end
	list:SetScript("OnSizeChanged", function(self) self:Build(); self:Redraw() end)
	return list
end

-- ---------------------------------------------------------------- the window
local function build()
	if main then return main end
	main = CreateFrame("Frame", "GlensAuctionsFrame", UIParent)
	main:SetSize(W, H)
	main:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 16, -110)
	main:SetFrameStrata("HIGH")
	main:SetToplevel(true)
	main:EnableMouse(true)
	main:SetMovable(true)
	main:SetClampedToScreen(true)
	main:Hide()

	local function piece(file, x, y, w)
		local t = main:CreateTexture(nil, "BACKGROUND")
		t:SetTexture(TEX .. file)
		t:SetSize(w, 256)
		t:SetPoint("TOPLEFT", x, y)
	end
	piece("AuctionFrameTopLeft", 0, 0, 256)
	piece("AuctionFrameTopMid", 256, 0, 320)
	piece("AuctionFrameTopRight", 576, 0, 256)
	piece("AuctionFrameBotLeft", 0, -256, 256)
	piece("AuctionFrameBotMid", 256, -256, 320)
	piece("AuctionFrameBotRight", 576, -256, 256)

	local portrait = main:CreateTexture(nil, "ARTWORK")
	portrait:SetSize(58, 58)
	portrait:SetPoint("TOPLEFT", 8, -7)
	portrait:SetTexture(TEX .. "AucAdvIcon")
	if portrait.SetMask then portrait:SetMask("Interface\\CharacterFrame\\TempPortraitAlphaMask") end

	-- title bar drags the window
	local drag = CreateFrame("Frame", nil, main)
	drag:SetPoint("TOPLEFT", 70, -12)
	drag:SetPoint("TOPRIGHT", -40, -12)
	drag:SetHeight(22)
	drag:EnableMouse(true)
	drag:RegisterForDrag("LeftButton")
	drag:SetScript("OnDragStart", function() main:StartMoving() end)
	drag:SetScript("OnDragStop", function() main:StopMovingOrSizing() end)
	main.title = GA:Text(drag, "normal", "CENTER")
	main.title:SetPoint("CENTER", 0, 0)

	local close = CreateFrame("Button", nil, main, "UIPanelCloseButton")
	close:SetPoint("CENTER", main, "TOPLEFT", W - 16, -22)
	close:SetScript("OnClick", function() main:Hide() end)

	local ver = GA:Text(main, "small", "RIGHT", { 0.55, 0.55, 0.55 })
	ver:SetPoint("BOTTOMRIGHT", -18, 14)
	ver:SetText("v" .. GA.VERSION .. " build " .. GA.BUILD)

	-- scan bar ----------------------------------------------------------------
	local scanBtn = GA:Button(main, "Scan", 80, 22, function()
		if IsShiftKeyDown() then GA:StartScan(true) else GA:StartScan() end
	end)
	scanBtn:SetPoint("TOPLEFT", 76, -40)
	scanBtn:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_BOTTOMRIGHT")
		GameTooltip:AddLine("Scan the auction house")
		GameTooltip:AddLine("Click: full scan (every listing - allowed about every 15 minutes)", 1, 1, 1, true)
		GameTooltip:AddLine("Shift-click: quick browse scan (lowest prices only)", 1, 1, 1, true)
		GameTooltip:Show()
	end)
	scanBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)

	local bar = CreateFrame("StatusBar", nil, main, "BackdropTemplate")
	bar:SetSize(340, 18)
	bar:SetPoint("LEFT", scanBtn, "RIGHT", 10, 0)
	bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
	bar:SetStatusBarColor(0.25, 0.55, 0.95)
	bar:SetMinMaxValues(0, 1)
	bar:SetValue(0)
	bar:SetBackdrop({ bgFile = TEX .. "BlackBack", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", edgeSize = 10, insets = { left = 2, right = 2, top = 2, bottom = 2 } })
	bar:SetBackdropColor(0, 0, 0, 0.6)
	local barText = GA:Text(bar, "small", "CENTER", { 1, 1, 1 })
	barText:SetPoint("CENTER")
	local status = GA:Text(main, "small", "LEFT", { 0.85, 0.85, 0.85 })
	status:SetPoint("LEFT", bar, "RIGHT", 10, 0)
	main.status = status

	local function refreshStatus()
		if not GA.realm then return end
		local n = 0
		for _ in pairs(GA.realm.items) do n = n + 1 end
		local cd = GA:ScanCooldownLeft()
		status:SetText(("%d items priced.  Last full scan: %s%s"):format(n, GA:Ago(GA.realm.lastFull),
			cd > 0 and ("  |cffaaaaaa(next in " .. math.ceil(cd / 60) .. " min)|r") or ""))
		if not GA.scan then
			bar:SetValue(GA.scanProgress or 0)
			barText:SetText(GA.scanText or "Ready")
		end
	end
	main.refreshStatus = refreshStatus
	GA:Listen("ScanProgress", function(frac, text) bar:SetValue(frac or 0); barText:SetText(text or "") end)
	GA:Listen("ScanDone", refreshStatus)
	main:SetScript("OnUpdate", function(self, el)
		self.t = (self.t or 0) + el
		if self.t > 5 then self.t = 0; refreshStatus() end
	end)

	local blizz = GA:Button(main, "Blizzard AH", 100, 22, function() GA:ShowBlizzard() end)
	blizz:SetPoint("TOPRIGHT", -40, -40)

	-- tabs --------------------------------------------------------------------
	local names = { { "appraiser", "Appraiser" }, { "settings", "Settings" } }
	main.numTabs = #names
	for i, n in ipairs(names) do
		local panel = CreateFrame("Frame", nil, main)
		panel:SetPoint("TOPLEFT", 22, -70)
		panel:SetPoint("BOTTOMRIGHT", -22, 30)
		panel:Hide()
		GA.panels[n[1]] = panel
		local tab = CreateFrame("Button", "GlensAuctionsFrameTab" .. i, main, "PanelTabButtonTemplate")
		tab:SetID(i)
		tab:SetText(n[2])
		tab.panelName = n[1]
		if i == 1 then tab:SetPoint("TOPLEFT", main, "BOTTOMLEFT", 15, 8) else tab:SetPoint("LEFT", GA.tabs[i - 1], "RIGHT", -14, 0) end
		tab:SetScript("OnClick", function(self) GA:ShowPanel(self.panelName) end)
		if PanelTemplates_TabResize then PanelTemplates_TabResize(tab, 0) end
		GA.tabs[i] = tab
	end
	if PanelTemplates_SetNumTabs then PanelTemplates_SetNumTabs(main, #names) end

	main:SetScript("OnShow", function() refreshStatus(); PlaySound(SOUNDKIT and SOUNDKIT.AUCTION_WINDOW_OPEN or 5274) end)
	main:SetScript("OnHide", function()
		if GA.switching then return end
		-- closing our window closes the auction house, like the classic one
		if GA.ahOpen and C_AuctionHouse.CloseAuctionHouse then C_AuctionHouse.CloseAuctionHouse() end
	end)

	GA:Fire("WindowBuilt", main)
	return main
end

function GA:ShowPanel(name)
	build()
	for i, tab in ipairs(self.tabs) do
		local on = tab.panelName == name
		self.panels[tab.panelName]:SetShown(on)
		if on and PanelTemplates_SetTab then PanelTemplates_SetTab(main, i) end
	end
	local titles = { appraiser = "Appraiser", settings = "Settings" }
	main.title:SetText("Glen's Auctions  -  " .. (titles[name] or ""))
	self.currentPanel = name
	self:Fire("PanelShown", name)
end

-- hide / restore Blizzard's auction house frame (it has to stay open for the auction house to work)
local function hideBlizzard()
	local f = AuctionHouseFrame
	if f and not f.gaHidden and not InCombatLockdown() then
		f.gaScale = f:GetScale()
		f:SetScale(0.001)
		f:SetAlpha(0)
		f.gaHidden = true
	end
end
local function showBlizzard()
	local f = AuctionHouseFrame
	if f and f.gaHidden and not InCombatLockdown() then
		f:SetScale(f.gaScale or 1)
		f:SetAlpha(1)
		f.gaHidden = nil
	end
end

function GA:ShowWindow(panel)
	build()
	if self.ahOpen then hideBlizzard() end
	main:Show()
	self:ShowPanel(panel or self.currentPanel or "appraiser")
end

function GA:ShowBlizzard()
	self.switching = true
	if main then main:Hide() end
	self.switching = false
	showBlizzard()
end

local function addBlizzardButton()
	local f = AuctionHouseFrame
	if not f or f.gaButton then return end
	local b = GA:Button(f, "Glen's Auctions", 120, 22, function() GA:ShowWindow() end)
	b:SetPoint("TOPRIGHT", f, "TOPRIGHT", -30, -1)
	b:SetFrameLevel(f:GetFrameLevel() + 20)
	f.gaButton = b
end

GA:Listen("AHOpen", function()
	addBlizzardButton()
	if GA.set.replaceBlizzard then
		C_Timer.After(0, function() GA:ShowWindow() end)
	end
end)
GA:Listen("AHClosed", function()
	GA.switching = true
	if main then main:Hide() end
	GA.switching = false
	showBlizzard()
end)
