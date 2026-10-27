-- ======================================================================
-- Installer body (SOURCES and LAYOUT are defined above by build_installer.py)
-- ======================================================================

local ChangeHistoryService = game:GetService("ChangeHistoryService")
local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Selection = game:GetService("Selection")
local ServerScriptService = game:GetService("ServerScriptService")
local ServerStorage = game:GetService("ServerStorage")
local StarterPack = game:GetService("StarterPack")
local StarterPlayer = game:GetService("StarterPlayer")
local Workspace = game:GetService("Workspace")

local TOOL_NAME = "Fortune Staff"
local TAG = "MoneyStaff"
local PARTS = { "Shaft", "Gold", "Ring", "Emerald", "Glow" }
local METAL = { Shaft = "Shaft", Gold = "Gold", Ring = "Gold" } -- part -> ColorKey if its texture is missing
local CRYSTAL = { Emerald = true }

local notes = {}
local function note(msg)
	table.insert(notes, msg)
	warn("[FortuneStaff] " .. msg)
end

local recording
pcall(function()
	recording = ChangeHistoryService:TryBeginRecording("Install Fortune Staff")
end)

-- ---------------------------------------------------------------- helpers

local function findImport(name)
	for _, inst in ipairs(Selection:Get()) do
		if inst.Name == name then
			return inst
		end
	end
	for _, inst in ipairs(Workspace:GetDescendants()) do
		if inst.Name == name and (inst:IsA("Model") or inst:IsA("Folder")) then
			return inst
		end
	end
	return nil
end

local function findPart(root, name)
	local exact = root:FindFirstChild(name, true)
	if exact and exact:IsA("BasePart") then
		return exact
	end
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("BasePart") and d.Name:sub(1, #name) == name then
			return d
		end
	end
	return nil
end

-- Marker cubes at Blender (0,0,0), (0,1,0), (0,0,1) reveal how the importer scaled / rotated the file.
local function markerFrame(model)
	local o, y, z = findPart(model, "Mark_O"), findPart(model, "Mark_Y"), findPart(model, "Mark_Z")
	assert(o and y and z, model.Name .. ": the Mark_O / Mark_Y / Mark_Z marker parts are missing (re-import the file)")
	local origin = o.Position
	local yv, zv = y.Position - origin, z.Position - origin
	return { O = origin, X = yv.Unit:Cross(zv.Unit), Y = yv.Unit, Z = zv.Unit, k = zv.Magnitude, markers = { o, y, z } }
end

local function toWorld(f, p)
	return f.O + (f.X * p[1] + f.Y * p[2] + f.Z * p[3]) * f.k
end

local function textureOf(part)
	if part:IsA("MeshPart") and part.TextureID ~= "" then
		return part.TextureID
	end
	local sa = part:FindFirstChildOfClass("SurfaceAppearance")
	if sa then
		local ok, id = pcall(function()
			return sa.ColorMap
		end)
		if ok and typeof(id) == "string" and id ~= "" then
			return id
		end
		ok, id = pcall(function()
			return sa.ColorMapContent.Uri
		end)
		if ok and typeof(id) == "string" and id ~= "" then
			return id
		end
	end
	return ""
end

local function clearSurfaceAppearance(part)
	for _, child in ipairs(part:GetChildren()) do
		if child:IsA("SurfaceAppearance") then
			child:Destroy()
		end
	end
end

local function make(className, props, parent)
	local inst = Instance.new(className)
	for k, v in pairs(props) do
		if k ~= "Attributes" then
			inst[k] = v
		end
	end
	for k, v in pairs(props.Attributes or {}) do
		inst:SetAttribute(k, v)
	end
	inst.Parent = parent
	return inst
end

local function ns(points)
	local keys = {}
	for _, p in ipairs(points) do
		table.insert(keys, NumberSequenceKeypoint.new(p[1], p[2]))
	end
	return NumberSequence.new(keys)
end

local function upsert(parent, className, name)
	local existing = parent:FindFirstChild(name)
	if existing and existing.ClassName == className then
		return existing
	end
	if existing then
		existing:Destroy()
	end
	return make(className, { Name = name }, parent)
end

local function upsertScript(parent, className, name, source, keepExisting)
	local existing = parent:FindFirstChild(name)
	if existing and keepExisting and existing:IsA(className) then
		return existing
	end
	if existing then
		existing:Destroy()
	end
	local s = Instance.new(className)
	s.Name = name
	s.Source = source
	s.Parent = parent
	return s
end

-- ---------------------------------------------------------------- scripts

local folder = upsert(ReplicatedStorage, "Folder", "MoneyStaff")
local configModule = upsertScript(folder, "ModuleScript", "Config", SOURCES.Config, true)
upsertScript(folder, "ModuleScript", "Layout", SOURCES.Layout, false)
upsertScript(folder, "ModuleScript", "StaffVFX", SOURCES.StaffVFX, false)
upsert(folder, "RemoteEvent", "Remote")
upsert(folder, "BindableEvent", "StaffHit")
local assetsFolder = upsert(folder, "Folder", "Assets")
upsertScript(ServerScriptService, "Script", "StaffServer", SOURCES.Server, false)
local playerScripts = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
	or make("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, StarterPlayer)
upsertScript(playerScripts, "LocalScript", "StaffClient", SOURCES.Client, false)

local okConfig, Config = pcall(require, configModule)
if not okConfig then
	note("Config has an error, using defaults for the install: " .. tostring(Config))
	Config = { Sounds = {}, FallbackTextures = {}, VFX = {} }
end
local vfxConfig = Config.VFX or {}

-- ---------------------------------------------------------------- effect textures

local vfxModel = findImport("MoneyStaffVFX")
if vfxModel then
	for key in pairs(assetsFolder:GetAttributes()) do
		assetsFolder:SetAttribute(key, nil)
	end
	local found = 0
	for _, key in ipairs(LAYOUT.textureKeys) do
		local carrier = findPart(vfxModel, "Tex_" .. key)
		local id = carrier and textureOf(carrier) or ""
		if id ~= "" then
			assetsFolder:SetAttribute("Tex_" .. key, id)
			found += 1
		end
	end
	if found < #LAYOUT.textureKeys then
		note(("only %d of %d effect textures came in with the import; missing ones use Roblox's built-in sparkle"):format(
			found,
			#LAYOUT.textureKeys
		))
	end
	vfxModel:Destroy()
else
	note("MoneyStaffVFX not found: import MoneyStaffVFX.fbx (or .glb) to bring in the effect textures, then run this again")
end

local function tex(key)
	local id = assetsFolder:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id
	end
	local fallbacks = Config.FallbackTextures or {}
	return fallbacks[key] or fallbacks.Default or "rbxasset://textures/particles/sparkles_main.dds"
end

-- ---------------------------------------------------------------- the staff

local model = findImport("MoneyStaff")
local tool

if model then
	local f = markerFrame(model)
	local parts = {}
	for _, name in ipairs(PARTS) do
		parts[name] = findPart(model, name)
		if not parts[name] then
			note("staff part missing: " .. name)
		end
	end
	assert(parts.Shaft, "MoneyStaff is missing its Shaft mesh")

	-- 1 Blender unit = STAFF_SCALE studs, whatever units the importer used
	local factor = LAYOUT.staffScale / f.k
	if math.abs(factor - 1) > 0.01 then
		local all = {}
		for _, p in pairs(parts) do
			table.insert(all, p)
		end
		for _, m in ipairs(f.markers) do
			table.insert(all, m)
		end
		for _, p in ipairs(all) do
			p.Size *= factor
			p.Position = f.O + (p.Position - f.O) * factor
		end
		f = markerFrame(model)
	end

	-- gold and the dark shaft keep their imported textures (polished metal); the emeralds get the
	-- crystal style; the glow inside them is Neon
	for name, p in pairs(parts) do
		p.CastShadow = METAL[name] ~= nil
		if METAL[name] then
			p.Material = Enum.Material.Metal
			if textureOf(p) == "" then
				p:SetAttribute("ColorKey", METAL[name])
			end
		elseif CRYSTAL[name] then
			p:SetAttribute("CrystalTexture", textureOf(p))
			clearSurfaceAppearance(p)
			p:SetAttribute("Crystal", true)
			p:SetAttribute("ColorKey", "Emerald")
		else
			clearSurfaceAppearance(p)
			if p:IsA("MeshPart") then
				p.TextureID = ""
			end
			p.Material = Enum.Material.Neon
			p:SetAttribute("ColorKey", "Glow")
		end
	end

	for _, container in ipairs({ StarterPack, ServerStorage }) do
		local old = container:FindFirstChild(TOOL_NAME)
		if old then
			old:Destroy()
		end
	end
	tool = make("Tool", {
		Name = TOOL_NAME,
		ToolTip = "Click: emerald slash combo  |  E: Jackpot",
		CanBeDropped = false,
		RequiresHandle = true,
		Attributes = { StaffScale = LAYOUT.staffScale },
	}, nil)
	CollectionService:AddTag(tool, TAG)

	local handle = parts.Shaft
	handle.Name = "Handle"
	local s = LAYOUT.staffScale
	local P = LAYOUT.points
	-- invisible volumes round the shaft and the head, for their motes and sparkles
	local shaftTop, shaftBottom = toWorld(f, P.ShaftTop), toWorld(f, P.ShaftBottom)
	local fxShaft = make("Part", {
		Name = "FXShaft",
		Transparency = 1,
		Size = Vector3.new(0.35 * s, (shaftTop - shaftBottom).Magnitude, 0.35 * s),
		CFrame = CFrame.fromMatrix((shaftTop + shaftBottom) / 2, f.X, f.Z),
	}, model)
	local fxHead = make("Part", {
		Name = "FXHead",
		Transparency = 1,
		Size = Vector3.new(1.3 * s, 1.15 * s, 0.7 * s),
		CFrame = CFrame.fromMatrix(toWorld(f, P.Head), f.X, f.Z),
	}, model)
	parts.FXShaft, parts.FXHead = fxShaft, fxHead

	for _, p in pairs(parts) do
		p.Anchored = false
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.Massless = true
		p.Parent = tool
	end
	for name, p in pairs(parts) do
		if p ~= handle and name ~= "Ring" then
			make("WeldConstraint", { Part0 = handle, Part1 = p }, handle)
		end
	end
	-- the gold rings hang on a Weld pivoting at the money symbol's centre, so StaffVFX can spin
	-- them round the main ring's own axis
	if parts.Ring then
		local ring = parts.Ring
		local pivot = CFrame.new(toWorld(f, P.Head)) * ring.CFrame.Rotation
		local axisWorld = (f.X * LAYOUT.ringAxis[1] + f.Y * LAYOUT.ringAxis[2] + f.Z * LAYOUT.ringAxis[3]).Unit
		local baseC0 = handle.CFrame:ToObjectSpace(pivot)
		make("Weld", {
			Name = "RingSpin",
			Part0 = handle,
			Part1 = ring,
			C0 = baseC0,
			C1 = ring.CFrame:ToObjectSpace(pivot),
			Attributes = { BaseC0 = baseC0, Axis = pivot:VectorToObjectSpace(axisWorld) },
		}, handle)
	end

	-- Grip: the hand round the lower shaft. GRIP_TILT turns the shaft up from "pointing ahead
	-- like a sword"; GRIP_SPIN turns the money symbol round the shaft.
	local gripPos = handle.CFrame:PointToObjectSpace(toWorld(f, P.Grip))
	tool.Grip = CFrame.fromMatrix(
		gripPos,
		handle.CFrame:VectorToObjectSpace(f.X),
		handle.CFrame:VectorToObjectSpace(f.Z)
	) * CFrame.Angles(math.rad(GRIP_TILT), math.rad(GRIP_SPIN), 0)

	local function attach(part, name, point)
		local a = make("Attachment", { Name = name }, part)
		a.WorldCFrame = CFrame.fromMatrix(toWorld(f, point), f.X, f.Z)
		return a
	end
	attach(handle, "Origin", { 0, 0, 0 })
	local aHead = attach(handle, "Head", P.Head)
	local aFinial = attach(handle, "Finial", P.Finial)
	local aUpper = attach(handle, "UpperGem", P.UpperGem)
	local aFoot = attach(handle, "FootGem", P.FootGem)

	-- the aura: soft emerald strands spiralling up the shaft (chains of curved camera-facing
	-- beams whose texture scrolls, so the energy keeps flowing)
	local auraOn = vfxConfig.Aura ~= false
	local flow = vfxConfig.AuraSpeed or 0.5
	local function auraChain(name, nodes, widthFn, props, parent)
		local atts = {}
		for i, p in ipairs(nodes) do
			local prev, nxt = nodes[math.max(1, i - 1)], nodes[math.min(#nodes, i + 1)]
			local t = (toWorld(f, nxt) - toWorld(f, prev)).Unit
			local up = math.abs(t:Dot(f.Y)) > 0.95 and f.X or f.Y
			atts[i] = make("Attachment", { Name = name .. i }, parent)
			atts[i].WorldCFrame = CFrame.fromMatrix(toWorld(f, p), t, (up - t * up:Dot(t)).Unit)
		end
		for i = 1, #atts - 1 do
			local a0, a1 = atts[i], atts[i + 1]
			local handleLength = (a1.WorldPosition - a0.WorldPosition).Magnitude / 3
			local beamProps = {
				Name = name,
				Attachment0 = a0,
				Attachment1 = a1,
				TextureMode = Enum.TextureMode.Wrap,
				TextureLength = 1.6 * s,
				CurveSize0 = handleLength,
				CurveSize1 = handleLength,
				Segments = 8,
				FaceCamera = true,
				LightInfluence = 0,
				Width0 = widthFn((i - 1) / (#atts - 1)) * s,
				Width1 = widthFn(i / (#atts - 1)) * s,
				Enabled = auraOn,
			}
			for k, v in pairs(props) do
				beamProps[k] = v
			end
			make("Beam", beamProps, parent)
		end
	end
	local function every(list, step)
		local out = {}
		for i = 1, #list, step do
			table.insert(out, list[i])
		end
		if out[#out] ~= list[#list] then
			table.insert(out, list[#list])
		end
		return out
	end
	for i, path in ipairs(LAYOUT.spirals) do
		local wmax = LAYOUT.spiralWidths[i]
		auraChain("AuraSpiral" .. i, every(path, 4), function(t)
			return 0.02 + wmax * 1.6 * math.sin(math.pi * t) ^ 0.8
		end, {
			Texture = tex("Wisp"),
			TextureSpeed = flow,
			LightEmission = 1,
			Transparency = NumberSequence.new(0.25),
			ZOffset = 0.1,
			Attributes = { TextureKey = "Wisp", Aura = true },
		}, handle)
	end

	-- small floating green / gold motes, occasional sparkles and little money symbols, close by
	local box = Enum.ParticleEmitterShape.Box
	local volume = Enum.ParticleEmitterShapeStyle.Volume
	local still = NumberRange.new(0)
	make("ParticleEmitter", {
		Name = "Motes",
		Texture = tex("Mote"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 5,
		Lifetime = NumberRange.new(1.0, 1.8),
		Speed = NumberRange.new(0.1, 0.3),
		SpreadAngle = Vector2.new(180, 180),
		Acceleration = Vector3.new(0, 0.5, 0),
		Size = ns({ { 0, 0 }, { 0.2, 0.06 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.2,
		Attributes = { TextureKey = "Mote" },
	}, fxShaft)
	make("ParticleEmitter", {
		Name = "Sparkles",
		Texture = tex("Sparkle"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 1.2,
		Lifetime = NumberRange.new(0.4, 0.7),
		Speed = still,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0 }, { 0.4, 0.14 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.3,
		Attributes = { TextureKey = "Sparkle" },
	}, fxShaft)
	make("ParticleEmitter", {
		Name = "Motes",
		Texture = tex("Mote"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 5,
		Lifetime = NumberRange.new(1.0, 1.6),
		Speed = NumberRange.new(0.1, 0.3),
		SpreadAngle = Vector2.new(180, 180),
		Acceleration = Vector3.new(0, 0.4, 0),
		Size = ns({ { 0, 0 }, { 0.2, 0.06 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.3,
		Attributes = { TextureKey = "Mote" },
	}, fxHead)
	make("ParticleEmitter", {
		Name = "Sparkles",
		Texture = tex("Sparkle"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 3,
		Lifetime = NumberRange.new(0.4, 0.7),
		Speed = still,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0 }, { 0.4, 0.18 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.4,
		Attributes = { TextureKey = "Sparkle" },
	}, fxHead)
	make("ParticleEmitter", {
		Name = "MoneySymbols",
		Texture = tex("Dollar"),
		Shape = box,
		ShapeStyle = Enum.ParticleEmitterShapeStyle.Surface,
		Rate = vfxConfig.MoneySymbols == false and 0 or 0.8,
		Lifetime = NumberRange.new(1.4, 2.0),
		Speed = NumberRange.new(0.15, 0.35),
		SpreadAngle = Vector2.new(180, 180),
		Acceleration = Vector3.new(0, 0.35, 0),
		Rotation = NumberRange.new(-15, 15),
		Size = ns({ { 0, 0 }, { 0.25, 0.2 * s }, { 0.75, 0.2 * s }, { 1, 0 } }),
		Transparency = ns({ { 0, 1 }, { 0.25, 0.15 }, { 0.75, 0.25 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.4,
		Attributes = { TextureKey = "Dollar" },
	}, fxHead)
	make("ParticleEmitter", {
		Name = "HeadGlow",
		Texture = tex("Glow"),
		Rate = 2,
		Lifetime = NumberRange.new(1.0),
		Speed = still,
		LockedToPart = true,
		Size = ns({ { 0, 1.3 * s }, { 0.5, 1.45 * s }, { 1, 1.3 * s } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.7 }, { 0.7, 0.7 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = -0.3,
		Attributes = { TextureKey = "Glow" },
	}, aHead)
	make("ParticleEmitter", {
		Name = "FootGlow",
		Texture = tex("Glow"),
		Rate = 2,
		Lifetime = NumberRange.new(1.0),
		Speed = still,
		LockedToPart = true,
		Size = ns({ { 0, 0.35 * s }, { 0.5, 0.42 * s }, { 1, 0.35 * s } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.6 }, { 0.7, 0.6 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = -0.1,
		Attributes = { TextureKey = "Glow" },
	}, aFoot)
	make("PointLight", {
		Name = "HeadLight",
		Range = 9 * s,
		Brightness = 1.4,
		Shadows = false,
		Attributes = { ColorKey = "Light" },
	}, aHead)
	-- bursts the attacks emit from the head
	make("ParticleEmitter", {
		Name = "SwingSparkles",
		Texture = tex("Sparkle"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 0,
		Lifetime = NumberRange.new(0.3, 0.55),
		Speed = NumberRange.new(4, 9),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 5,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0.28 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Attributes = { TextureKey = "Sparkle" },
	}, fxHead)
	make("ParticleEmitter", {
		Name = "SwingCoins",
		Texture = tex("Coin"),
		Shape = box,
		ShapeStyle = volume,
		Rate = 0,
		Lifetime = NumberRange.new(0.6, 0.9),
		Speed = NumberRange.new(4, 8),
		SpreadAngle = Vector2.new(70, 70),
		Acceleration = Vector3.new(0, -20, 0),
		Rotation = NumberRange.new(-180, 180),
		RotSpeed = NumberRange.new(-400, 400),
		Size = ns({ { 0, 0.22 * s }, { 1, 0.2 * s } }),
		Transparency = ns({ { 0, 0 }, { 0.8, 0 }, { 1, 1 } }),
		LightEmission = 0.15,
		LightInfluence = 0,
		Attributes = { TextureKey = "Coin" },
	}, fxHead)

	-- swing trails from the upper gem to the finial, sweeping the head through the air
	make("Trail", {
		Name = "SwingTrail",
		Attachment0 = aUpper,
		Attachment1 = aFinial,
		Texture = tex("Trail"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.2,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 0.8,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "Trail", SwingTrail = true },
	}, handle)
	make("Trail", {
		Name = "SwingGlow",
		Attachment0 = aUpper,
		Attachment1 = aFinial,
		Texture = tex("Glow"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.28,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0.55 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "Glow", SwingTrail = true },
	}, handle)

	local sounds = Config.Sounds or {}
	for name, loudness in pairs({ Equip = 0.5, Swing = 0.6, Special = 0.8 }) do
		make("Sound", { Name = name .. "Sound", SoundId = sounds[name] or "", Volume = loudness }, handle)
	end

	for _, m in ipairs(f.markers) do
		m:Destroy()
	end
	model:Destroy()

	tool.Parent = StarterPack
	local copy = tool:Clone()
	copy.Parent = ServerStorage
	local okVfx, VFX = pcall(require, folder:FindFirstChild("StaffVFX"))
	if okVfx then
		VFX.ApplyColors(tool)
		VFX.ApplyColors(copy)
	else
		note("could not preview the colours in Studio (" .. tostring(VFX) .. "); they apply in game")
	end
	Selection:Set({ tool })
else
	tool = StarterPack:FindFirstChild(TOOL_NAME)
	if tool then
		note("MoneyStaff not found, so only the scripts were updated (the existing staff was kept)")
	else
		note("MoneyStaff not found: import MoneyStaff.fbx (or .glb) with the 3D Importer, then run this again")
	end
end

if recording then
	pcall(function()
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end)
end

print(("[FortuneStaff] Install finished%s. Staff: %s | Scripts: ReplicatedStorage.MoneyStaff, "):format(
	#notes > 0 and (" with " .. #notes .. " note(s) above") or "",
	tool and tool:GetFullName() or "not built"
) .. "ServerScriptService.StaffServer, StarterPlayerScripts.StaffClient")
