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

local TOOL_NAME = "Mo Feng Blade"
local TAG = "MoFengSword"
local SWORD_PARTS = { "Handle", "Hilt", "BladeCore", "BladeEdge", "BladeRunes", "EnergyVeins", "AccentGems", "BladeAura" }
local NEON_ROLES = { BladeEdge = "Primary", BladeRunes = "Core", EnergyVeins = "Vein", AccentGems = "Accent" }
local TEXTURED = { "Handle", "Hilt", "BladeCore" }

local notes = {}
local function note(msg)
	table.insert(notes, msg)
	warn("[Mo Feng] " .. msg)
end

local recording
pcall(function()
	recording = ChangeHistoryService:TryBeginRecording("Install Mo Feng Blade")
end)

-- ---------------------------------------------------------------- finding the imports

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

-- The exports carry three tiny marker cubes at Blender (0,0,0), (0,1,0), (0,0,1).
-- They tell us exactly how the importer scaled and rotated the file.
local function markerFrame(model)
	local o, y, z = findPart(model, "Mark_O"), findPart(model, "Mark_Y"), findPart(model, "Mark_Z")
	assert(o and y and z, model.Name .. ": the Mark_O / Mark_Y / Mark_Z marker parts are missing (re-import the file)")
	local origin = o.Position
	local yv, zv = y.Position - origin, z.Position - origin
	local xu = yv.Unit:Cross(zv.Unit)
	return { O = origin, X = xu, Y = yv.Unit, Z = zv.Unit, k = zv.Magnitude, markers = { o, y, z } }
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

-- Keep the imported texture, but as TextureID (scripts can swap it for the gold theme).
local function useTextureID(part, label)
	local id = textureOf(part)
	clearSurfaceAppearance(part)
	if part:IsA("MeshPart") and id ~= "" then
		part.TextureID = id
	elseif id == "" then
		note(label .. " came in without its texture; set its TextureID to the matching PNG from the textures folder")
	end
	return id
end

local function stripTexture(part)
	clearSurfaceAppearance(part)
	if part:IsA("MeshPart") then
		part.TextureID = ""
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

local folder = upsert(ReplicatedStorage, "Folder", "MoFengSword")
local configModule = upsertScript(folder, "ModuleScript", "Config", SOURCES.Config, true)
upsertScript(folder, "ModuleScript", "SwordVFX", SOURCES.SwordVFX, false)
upsert(folder, "RemoteEvent", "Remote")
upsert(folder, "BindableEvent", "SwordHit")
local assetsFolder = upsert(folder, "Folder", "Assets")
upsertScript(ServerScriptService, "Script", "MoFengSwordServer", SOURCES.Server, false)
local playerScripts = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
	or make("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, StarterPlayer)
upsertScript(playerScripts, "LocalScript", "MoFengSwordClient", SOURCES.Client, false)

local okConfig, Config = pcall(require, configModule)
if not okConfig then
	note("Config has an error, using defaults for the install: " .. tostring(Config))
	Config = { DefaultTheme = "Cyan", Sounds = {}, FallbackTextures = {} }
end

-- ---------------------------------------------------------------- VFX assets

local vfxModel = findImport("MoFengVFX")
if vfxModel then
	assetsFolder:ClearAllChildren()
	for key in pairs(assetsFolder:GetAttributes()) do
		assetsFolder:SetAttribute(key, nil)
	end
	local f = markerFrame(vfxModel)
	local toBlender = CFrame.fromMatrix(Vector3.zero, f.X, f.Y)
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
		note(("only %d of %d VFX textures came in with the import; missing ones use Roblox's built-in sparkle"):format(
			found,
			#LAYOUT.textureKeys
		))
	end
	for _, name in ipairs(LAYOUT.vfxAssets) do
		local part = findPart(vfxModel, name)
		if part then
			if name == "SlashArc" or name == "ShockRing" or name:sub(1, 4) == "Rock" then
				useTextureID(part, name)
			else
				stripTexture(part)
			end
			part.Size = part.Size / f.k -- 1 Blender unit = 1 stud
			part:SetAttribute("BlenderToLocal", part.CFrame.Rotation:Inverse() * toBlender)
			local pivot = LAYOUT.pivots[name]
			if pivot then
				part:SetAttribute("PivotOffset", Vector3.new(pivot[1], pivot[2], pivot[3]))
			end
			part.Material = (name == "SlashArc" or name == "ShockRing") and Enum.Material.ForceField
				or (name:sub(1, 4) == "Rock" and Enum.Material.SmoothPlastic or Enum.Material.Neon)
			part.Anchored = true
			part.CanCollide = false
			part.CanQuery = false
			part.CanTouch = false
			part.CastShadow = false
			part.Name = name
			part.Parent = assetsFolder
		else
			note("VFX mesh missing from MoFengVFX: " .. name)
		end
	end
	vfxModel:Destroy()
else
	note("MoFengVFX not found: import MoFengVFX.fbx (or .glb) for slashes, rings, shards and textures, then run this again")
end

-- ---------------------------------------------------------------- the sword

local function tex(key)
	local id = assetsFolder:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id
	end
	local fallbacks = Config.FallbackTextures or {}
	return fallbacks[key] or fallbacks.Default or "rbxasset://textures/particles/sparkles_main.dds"
end

local swordModel = findImport("MoFengSword")
local tool

if swordModel then
	local f = markerFrame(swordModel)
	local parts = {}
	for _, name in ipairs(SWORD_PARTS) do
		parts[name] = findPart(swordModel, name)
		if not parts[name] then
			note("sword part missing: " .. name)
		end
	end
	assert(parts.Handle and parts.BladeEdge, "MoFengSword is missing its Handle or BladeEdge mesh")

	-- 1 Blender unit = 1 stud (the importer may have converted units)
	local factor = LAYOUT.swordScale / f.k
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
		f = markerFrame(swordModel)
	end

	for _, name in ipairs(TEXTURED) do
		if parts[name] then
			useTextureID(parts[name], name)
			parts[name].Material = Enum.Material.SmoothPlastic
			parts[name].Color = Color3.new(1, 1, 1)
		end
	end
	if parts.Hilt and parts.Hilt.TextureID ~= "" then
		assetsFolder:SetAttribute("Tex_HiltSilver", parts.Hilt.TextureID)
	end
	for name, role in pairs(NEON_ROLES) do
		local p = parts[name]
		if p then
			stripTexture(p)
			p.Material = Enum.Material.Neon
			p.CastShadow = false
			p:SetAttribute("ColorRole", role)
		end
	end
	if parts.BladeAura then
		useTextureID(parts.BladeAura, "BladeAura")
		parts.BladeAura.Material = Enum.Material.ForceField
		parts.BladeAura.CastShadow = false
		parts.BladeAura:SetAttribute("ColorRole", "Primary")
	end

	for _, container in ipairs({ StarterPack, ServerStorage }) do
		local old = container:FindFirstChild(TOOL_NAME)
		if old then
			old:Destroy()
		end
	end
	tool = make("Tool", {
		Name = TOOL_NAME,
		ToolTip = "Click: slash combo  |  E: special",
		CanBeDropped = false,
		RequiresHandle = true,
		Attributes = {
			Theme = Config.DefaultTheme or "Cyan",
			SwordScale = LAYOUT.swordScale,
			BladeHalfWidth = LAYOUT.points.BladeHalfWidth * LAYOUT.swordScale,
		},
	}, nil)
	CollectionService:AddTag(tool, TAG)

	local handle = parts.Handle
	for _, p in pairs(parts) do
		p.Anchored = false
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.Massless = true
		p.Parent = tool
	end
	for _, p in pairs(parts) do
		if p ~= handle then
			make("WeldConstraint", { Part0 = handle, Part1 = p }, handle)
		end
	end

	-- Grip: hand on the upper grip, blade pointing up the hand's grip axis,
	-- flat of the blade facing forward (what the camera sees in third person).
	local P = LAYOUT.points
	local gripPos = handle.CFrame:PointToObjectSpace(toWorld(f, P.Grip))
	local bladeDir = handle.CFrame:VectorToObjectSpace(f.Z)
	local widthDir = handle.CFrame:VectorToObjectSpace(f.X)
	tool.Grip = CFrame.fromMatrix(gripPos, widthDir, bladeDir)

	local function attach(part, name, point)
		local a = make("Attachment", { Name = name }, part)
		a.WorldCFrame = CFrame.fromMatrix(toWorld(f, point), f.X, f.Z)
		return a
	end
	local edge = parts.BladeEdge
	local hilt = parts.Hilt or handle
	local aBase = attach(edge, "BladeBase", P.BladeBase)
	local aTip = attach(edge, "BladeTip", P.BladeTip)
	attach(edge, "BladeMid", P.BladeMid)
	local aFlow0 = attach(edge, "FlowStart", P.FlowStart)
	local aFlow1 = attach(edge, "FlowEnd", P.FlowEnd)
	local aGuard = attach(hilt, "GuardCenter", P.GuardCenter)
	local aPommel = attach(hilt, "Pommel", P.Pommel)

	local box = Enum.ParticleEmitterShape.Box
	local volume = Enum.ParticleEmitterShapeStyle.Volume
	local surface = Enum.ParticleEmitterShapeStyle.Surface

	-- idle aura: flame wisps licking off the blade
	make("ParticleEmitter", {
		Name = "AuraWisps",
		Texture = tex("Wisp"),
		FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot,
		Rate = 22,
		Lifetime = NumberRange.new(0.55, 0.9),
		Speed = NumberRange.new(0.4, 1.0),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = volume,
		Acceleration = Vector3.new(0, 2.5, 0),
		Drag = 3,
		Size = ns({ { 0, 0.15 }, { 0.3, 0.42 }, { 1, 0.1 } }),
		Transparency = ns({ { 0, 1 }, { 0.15, 0.35 }, { 1, 1 } }),
		Rotation = NumberRange.new(-180, 180),
		RotSpeed = NumberRange.new(-90, 90),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.3,
		Attributes = { ColorRole = "Primary", ColorRole2 = "Vein", TextureKey = "Wisp", Flipbook = true },
	}, edge)
	-- floating motes drifting upward
	make("ParticleEmitter", {
		Name = "Motes",
		Texture = tex("Ember"),
		Rate = 10,
		Lifetime = NumberRange.new(1.2, 2.2),
		Speed = NumberRange.new(0.1, 0.4),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = volume,
		Acceleration = Vector3.new(0, 1.4, 0),
		Size = ns({ { 0, 0.08 }, { 0.5, 0.12 }, { 1, 0 } }),
		Transparency = ns({ { 0, 1 }, { 0.2, 0 }, { 0.8, 0.2 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Attributes = { ColorRole = "Core", ColorRole2 = "Primary", TextureKey = "Ember" },
	}, edge)
	-- burst emitters (Rate 0, fired from scripts)
	make("ParticleEmitter", {
		Name = "SwingSparks",
		Texture = tex("Spark"),
		Orientation = Enum.ParticleOrientation.VelocityParallel,
		Rate = 0,
		Lifetime = NumberRange.new(0.25, 0.45),
		Speed = NumberRange.new(10, 18),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = surface,
		Drag = 5,
		Acceleration = Vector3.new(0, -8, 0),
		Size = ns({ { 0, 0.2 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Attributes = { ColorRole = "Core", ColorRole2 = "Primary", TextureKey = "Spark" },
	}, edge)
	make("ParticleEmitter", {
		Name = "Fragments",
		Texture = tex("Star"),
		Rate = 0,
		Lifetime = NumberRange.new(0.4, 0.7),
		Speed = NumberRange.new(6, 11),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = volume,
		Drag = 3,
		Acceleration = Vector3.new(0, -12, 0),
		Rotation = NumberRange.new(0, 360),
		RotSpeed = NumberRange.new(-300, 300),
		Size = ns({ { 0, 0.16 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 0.8, 0.3 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Attributes = { ColorRole = "Vein", ColorRole2 = "Primary", TextureKey = "Star" },
	}, edge)
	make("ParticleEmitter", {
		Name = "Crackle",
		Texture = tex("Spark"),
		Orientation = Enum.ParticleOrientation.VelocityParallel,
		Rate = 0,
		Lifetime = NumberRange.new(0.15, 0.3),
		Speed = NumberRange.new(3, 6),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = surface,
		Size = ns({ { 0, 0.14 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Attributes = { ColorRole = "Core", ColorRole2 = "Vein", TextureKey = "Spark" },
	}, edge)
	-- soft glow around the guard and the pommel gem
	make("ParticleEmitter", {
		Name = "GuardHalo",
		Texture = tex("Glow"),
		Rate = 4,
		Lifetime = NumberRange.new(0.6),
		Speed = NumberRange.new(0),
		LockedToPart = true,
		Size = ns({ { 0, 1.2 }, { 0.5, 1.5 }, { 1, 1.2 } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.8 }, { 0.7, 0.8 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = -0.5,
		Attributes = { ColorRole = "Primary", TextureKey = "Glow" },
	}, aGuard)
	make("ParticleEmitter", {
		Name = "PommelHalo",
		Texture = tex("Glow"),
		Rate = 4,
		Lifetime = NumberRange.new(0.6),
		Speed = NumberRange.new(0),
		LockedToPart = true,
		Size = ns({ { 0, 0.55 }, { 0.5, 0.7 }, { 1, 0.55 } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.7 }, { 0.7, 0.7 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Attributes = { ColorRole = "Accent", TextureKey = "Glow" },
	}, aPommel)
	make("ParticleEmitter", {
		Name = "TipGlint",
		Texture = tex("Star"),
		Rate = 0.8,
		Lifetime = NumberRange.new(0.35),
		Speed = NumberRange.new(0),
		LockedToPart = true,
		Rotation = NumberRange.new(0, 360),
		Size = ns({ { 0, 0 }, { 0.4, 0.7 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 1, 0.2 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.5,
		Attributes = { ColorRole = "Core", TextureKey = "Star" },
	}, aTip)
	-- swing trails: bright core plus a longer soft glow
	make("Trail", {
		Name = "TrailCore",
		Attachment0 = aBase,
		Attachment1 = aTip,
		Texture = tex("Trail"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.16,
		MinLength = 0.05,
		FaceCamera = false,
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		WidthScale = ns({ { 0, 1 }, { 1, 0.6 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { ColorRole = "Core", ColorRole2 = "Primary", TextureKey = "Trail" },
	}, edge)
	make("Trail", {
		Name = "TrailGlow",
		Attachment0 = aBase,
		Attachment1 = aTip,
		Texture = tex("Trail"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.28,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0.45 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { ColorRole = "Primary", TextureKey = "Trail" },
	}, edge)
	-- energy flowing up the blade, and a soft glow around it
	make("Beam", {
		Name = "FlowBeam",
		Attachment0 = aFlow0,
		Attachment1 = aFlow1,
		Texture = tex("Beam"),
		TextureMode = Enum.TextureMode.Wrap,
		TextureLength = 1.2,
		TextureSpeed = 1.6,
		Width0 = 0.36,
		Width1 = 0.16,
		FaceCamera = true,
		Segments = 10,
		LightEmission = 1,
		LightInfluence = 0,
		Transparency = ns({ { 0, 0.35 }, { 0.5, 0.15 }, { 1, 0.4 } }),
		ZOffset = 0.05,
		Attributes = { ColorRole = "Core", ColorRole2 = "Primary", TextureKey = "Beam" },
	}, edge)
	make("Beam", {
		Name = "GlowBeam",
		Attachment0 = aFlow0,
		Attachment1 = aFlow1,
		Texture = tex("Glow"),
		TextureMode = Enum.TextureMode.Stretch,
		Width0 = 1.0,
		Width1 = 0.55,
		FaceCamera = true,
		LightEmission = 1,
		LightInfluence = 0,
		Transparency = NumberSequence.new(0.78),
		Attributes = { ColorRole = "Primary", TextureKey = "Glow" },
	}, edge)
	make("PointLight", {
		Name = "BladeLight",
		Range = 9,
		Brightness = 1.6,
		Shadows = false,
		Attributes = { ColorRole = "Primary" },
	}, edge)
	make("PointLight", {
		Name = "GemLight",
		Range = 4,
		Brightness = 1.2,
		Shadows = false,
		Attributes = { ColorRole = "Accent" },
	}, aPommel)

	local sounds = Config.Sounds or {}
	for name, loudness in pairs({ Equip = 0.5, Swing = 0.6, Special = 0.8 }) do
		make("Sound", { Name = name .. "Sound", SoundId = sounds[name] or "", Volume = loudness }, handle)
	end

	local s = LAYOUT.swordScale
	if math.abs(s - 1) > 1e-3 then
		for _, d in ipairs(tool:GetDescendants()) do
			if d:IsA("ParticleEmitter") then
				local keys = {}
				for _, kp in ipairs(d.Size.Keypoints) do
					table.insert(keys, NumberSequenceKeypoint.new(kp.Time, kp.Value * s, kp.Envelope * s))
				end
				d.Size = NumberSequence.new(keys)
				d.Speed = NumberRange.new(d.Speed.Min * s, d.Speed.Max * s)
			elseif d:IsA("Beam") then
				d.Width0 *= s
				d.Width1 *= s
			elseif d:IsA("PointLight") then
				d.Range *= s
			end
		end
	end

	for _, m in ipairs(f.markers) do
		m:Destroy()
	end
	swordModel:Destroy()

	tool.Parent = StarterPack
	local copy = tool:Clone()
	copy.Parent = ServerStorage
	local okVfx, SwordVFX = pcall(require, folder:FindFirstChild("SwordVFX"))
	if okVfx then
		SwordVFX.ApplyTheme(tool)
		SwordVFX.ApplyTheme(copy)
	else
		note("could not preview the theme colours in Studio (" .. tostring(SwordVFX) .. "); they apply in game")
	end
	Selection:Set({ tool })
else
	tool = StarterPack:FindFirstChild(TOOL_NAME)
	if tool then
		note("MoFengSword not found, so only the scripts were updated (the existing sword was kept)")
	else
		note("MoFengSword not found: import MoFengSword.fbx (or .glb) with the 3D Importer, then run this again")
	end
end

if recording then
	pcall(function()
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end)
end

print(("[Mo Feng] Install finished%s. Sword: %s | Scripts: ReplicatedStorage.MoFengSword, "):format(
	#notes > 0 and (" with " .. #notes .. " note(s) above") or "",
	tool and tool:GetFullName() or "not built"
) .. "ServerScriptService.MoFengSwordServer, StarterPlayerScripts.MoFengSwordClient")
