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

local TOOL_NAME = "Starburst Blade"
local TAG = "StarburstSword"
local SWORD_PARTS = { "Handle", "Shell", "GlowOrange", "GlowYellow", "FlameRed", "Sparkles", "Aura" }
-- The sword is drawn by effects (beams and particles). The meshes are only a faint Neon base
-- underneath (Config.VFX.MeshTransparency), so nothing reads as a solid object.
local COLOR_KEYS = {
	Handle = "Handle",
	Shell = "Ink",
	GlowOrange = "Orange",
	GlowYellow = "Yellow",
	FlameRed = "Red",
	Sparkles = "Sparkle",
}

local notes = {}
local function note(msg)
	table.insert(notes, msg)
	warn("[Starburst] " .. msg)
end

local recording
pcall(function()
	recording = ChangeHistoryService:TryBeginRecording("Install Starburst Blade")
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

local folder = upsert(ReplicatedStorage, "Folder", "StarburstSword")
local configModule = upsertScript(folder, "ModuleScript", "Config", SOURCES.Config, true)
upsertScript(folder, "ModuleScript", "Layout", SOURCES.Layout, false)
upsertScript(folder, "ModuleScript", "StarburstVFX", SOURCES.StarburstVFX, false)
upsert(folder, "RemoteEvent", "Remote")
upsert(folder, "BindableEvent", "SwordHit")
local assetsFolder = upsert(folder, "Folder", "Assets")
upsertScript(ServerScriptService, "Script", "StarburstServer", SOURCES.Server, false)
local playerScripts = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
	or make("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, StarterPlayer)
upsertScript(playerScripts, "LocalScript", "StarburstClient", SOURCES.Client, false)

local okConfig, Config = pcall(require, configModule)
if not okConfig then
	note("Config has an error, using defaults for the install: " .. tostring(Config))
	Config = { Sounds = {}, FallbackTextures = {} }
end

-- ---------------------------------------------------------------- VFX textures

local vfxModel = findImport("StarburstVFX")
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
	note("StarburstVFX not found: import StarburstVFX.fbx (or .glb) to bring in the effect textures, then run this again")
end

local function tex(key)
	local id = assetsFolder:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id
	end
	local fallbacks = Config.FallbackTextures or {}
	return fallbacks[key] or fallbacks.Default or "rbxasset://textures/particles/sparkles_main.dds"
end

-- ---------------------------------------------------------------- the sword

local swordModel = findImport("StarburstSword")
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
	assert(parts.Handle and parts.Shell, "StarburstSword is missing its Handle or Shell mesh")

	-- 1 Blender unit = SWORD_SCALE studs, whatever units the importer used
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

	local meshTransparency = (Config.VFX and Config.VFX.MeshTransparency) or 0.8
	for name, key in pairs(COLOR_KEYS) do
		local p = parts[name]
		if p then
			clearSurfaceAppearance(p)
			if p:IsA("MeshPart") then
				p.TextureID = ""
			end
			p.Material = Enum.Material.Neon
			p.CastShadow = false
			p.Transparency = meshTransparency
			p:SetAttribute("ColorKey", key)
		end
	end
	if parts.Aura then
		local id = textureOf(parts.Aura)
		clearSurfaceAppearance(parts.Aura)
		if id ~= "" then
			parts.Aura.TextureID = id
		end
		parts.Aura.Material = Enum.Material.ForceField
		parts.Aura.CastShadow = false
		parts.Aura:SetAttribute("ColorKey", "Aura")
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
		Attributes = { SwordScale = LAYOUT.swordScale },
	}, nil)
	CollectionService:AddTag(tool, TAG)

	local handle = parts.Handle
	local s = LAYOUT.swordScale
	-- invisible volume along the blade, for the blade's particle emitters
	local vol = LAYOUT.bladeVolume
	local fx = make("Part", {
		Name = "FXBlade",
		Transparency = 1,
		Size = Vector3.new(vol.size[1], vol.size[3], vol.size[2]) * s,
		CFrame = CFrame.fromMatrix(toWorld(f, vol.centre), f.X, f.Z),
	}, swordModel)
	parts.FXBlade = fx

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

	-- Grip: hand on the handle below the star, blade up the hand's grip axis,
	-- flat of the sword facing forward (what the camera sees in third person).
	local P = LAYOUT.points
	local gripPos = handle.CFrame:PointToObjectSpace(toWorld(f, P.Grip))
	tool.Grip = CFrame.fromMatrix(
		gripPos,
		handle.CFrame:VectorToObjectSpace(f.X),
		handle.CFrame:VectorToObjectSpace(f.Z)
	)

	local function attach(part, name, point)
		local a = make("Attachment", { Name = name }, part)
		a.WorldCFrame = CFrame.fromMatrix(toWorld(f, point), f.X, f.Z)
		return a
	end
	local shell = parts.Shell
	local aStar = attach(shell, "Star", P.Star)
	local aBladeStart = attach(fx, "BladeStart", P.BladeStart)
	local aTip = attach(fx, "BladeTip", P.BladeTip)
	local aTrailBase = attach(fx, "TrailBase", P.TrailBase)
	local aHandleStart = attach(shell, "HandleStart", P.HandleStart)
	local aHandleEnd = attach(shell, "HandleEnd", P.HandleEnd)
	-- the two blended energy circles (round the eye and round the top of the handle) and where they meet
	local aRingA = attach(shell, "RingA", P.RingA)
	local aRingB = attach(shell, "RingB", P.RingB)
	local aJunction = attach(shell, "Junction", P.Junction)

	-- the painted look: the blade and handle drawn by camera-facing beams, exactly as in the reference
	make("Beam", {
		Name = "BladePaint",
		Attachment0 = aBladeStart,
		Attachment1 = aTip,
		Texture = tex("BladePaint"),
		TextureMode = Enum.TextureMode.Stretch,
		Width0 = LAYOUT.bladePaintWidth * s,
		Width1 = LAYOUT.bladePaintWidth * s,
		FaceCamera = true,
		Segments = 1,
		LightEmission = 0.15,
		LightInfluence = 0,
		ZOffset = 0.15,
		Attributes = { TextureKey = "BladePaint" },
	}, fx)
	make("Beam", {
		Name = "HandlePaint",
		Attachment0 = aHandleStart,
		Attachment1 = aHandleEnd,
		Texture = tex("HandlePaint"),
		TextureMode = Enum.TextureMode.Stretch,
		Width0 = LAYOUT.handlePaintWidth * s,
		Width1 = LAYOUT.handlePaintWidth * s,
		FaceCamera = true,
		Segments = 1,
		LightEmission = 0.15,
		LightInfluence = 0,
		ZOffset = 0.15,
		Attributes = { TextureKey = "HandlePaint" },
	}, shell)
	make("Beam", {
		Name = "BladeGlow",
		Attachment0 = aTrailBase,
		Attachment1 = aTip,
		Texture = tex("Glow"),
		TextureMode = Enum.TextureMode.Stretch,
		Width0 = 1.0 * s,
		Width1 = 0.3 * s,
		FaceCamera = true,
		LightEmission = 1,
		LightInfluence = 0,
		Transparency = NumberSequence.new(0.55),
		ZOffset = -0.2,
		Attributes = { TextureKey = "Glow" },
	}, fx)

	-- energy flowing through the blade and handle, and the star's spikes as beams of light
	local function energyBeam(name, a0, a1, key, w0, w1, extra, parent)
		local props = {
			Name = name,
			Attachment0 = a0,
			Attachment1 = a1,
			Texture = tex(key),
			TextureMode = Enum.TextureMode.Stretch,
			Width0 = w0 * s,
			Width1 = w1 * s,
			FaceCamera = true,
			Segments = 1,
			LightEmission = 1,
			LightInfluence = 0,
			ZOffset = 0.22,
			Attributes = { TextureKey = key },
		}
		for k, v in pairs(extra or {}) do
			props[k] = v
		end
		return make("Beam", props, parent)
	end
	local flowing = { TextureMode = Enum.TextureMode.Wrap, TextureLength = 0.9 * s, TextureSpeed = 1.4, ZOffset = 0.18 }
	energyBeam("BladeFlow", aBladeStart, aTip, "EnergyFlow", 0.24, 0.015, flowing, fx)
	energyBeam("BladeCore", aBladeStart, aTip, "FlowStroke", 0.09, 0.014, nil, fx)
	energyBeam("HandleFlow", aHandleStart, aHandleEnd, "EnergyFlow", 0.14, 0.014, flowing, shell)
	energyBeam("HandleCore", aHandleStart, aHandleEnd, "FlowStroke", 0.06, 0.012, nil, shell)
	for i, sb in ipairs(LAYOUT.spikeBeams) do
		energyBeam(
			"SpikeGlow" .. i,
			attach(shell, "SpikeBase" .. i, sb.base),
			attach(shell, "SpikeTip" .. i, sb.tip),
			"EnergySpike",
			sb.width,
			sb.width,
			{ ZOffset = 0.2, Attributes = { TextureKey = "EnergySpike", Spike = true } },
			shell
		)
	end

	local box = Enum.ParticleEmitterShape.Box
	-- soft energy wisps curling off the blade and dissolving
	make("ParticleEmitter", {
		Name = "EnergyWisps",
		Texture = tex("EnergyWisp"),
		FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot,
		Rate = 14,
		Lifetime = NumberRange.new(0.5, 0.8),
		Speed = NumberRange.new(0.3, 0.8),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = Enum.ParticleEmitterShapeStyle.Surface,
		Acceleration = Vector3.new(0, 2.5, 0),
		Drag = 2,
		Size = ns({ { 0, 0.14 * s }, { 0.4, 0.26 * s }, { 1, 0.2 * s } }),
		Rotation = NumberRange.new(-20, 20),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.3,
		Attributes = { TextureKey = "EnergyWisp", Flipbook = true },
	}, fx)
	make("ParticleEmitter", {
		Name = "Embers",
		Texture = tex("Ember"),
		Rate = 8,
		Lifetime = NumberRange.new(0.9, 1.6),
		Speed = NumberRange.new(0.2, 0.6),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
		Acceleration = Vector3.new(0, 1.8, 0),
		Size = ns({ { 0, 0.09 * s }, { 0.5, 0.12 * s }, { 1, 0 } }),
		Transparency = ns({ { 0, 1 }, { 0.15, 0 }, { 0.8, 0.2 }, { 1, 1 } }),
		LightEmission = 0.8,
		LightInfluence = 0,
		Attributes = { TextureKey = "Ember" },
	}, fx)
	make("ParticleEmitter", {
		Name = "Twinkles",
		Texture = tex("Twinkle"),
		Rate = 9,
		Lifetime = NumberRange.new(0.35, 0.6),
		Speed = NumberRange.new(0.05, 0.25),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0 }, { 0.4, 0.14 * s }, { 1, 0 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.4,
		Attributes = { TextureKey = "Twinkle" },
	}, fx)
	make("ParticleEmitter", {
		Name = "SwingSparks",
		Texture = tex("Spark"),
		Orientation = Enum.ParticleOrientation.VelocityParallel,
		Rate = 0,
		Lifetime = NumberRange.new(0.25, 0.45),
		Speed = NumberRange.new(10, 18),
		SpreadAngle = Vector2.new(180, 180),
		Shape = box,
		ShapeStyle = Enum.ParticleEmitterShapeStyle.Surface,
		Drag = 5,
		Acceleration = Vector3.new(0, -8, 0),
		Size = ns({ { 0, 0.28 * s }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 0.6,
		LightInfluence = 0,
		Attributes = { TextureKey = "Spark" },
	}, fx)
	-- the star: two soft energy rings that overlap and melt into each other, one figure-8
	-- stream of energy running round both (its bright heads are added in game by StarburstVFX),
	-- the dark eye in the top ring, a white-hot core where the rings meet, fragments and pulses
	local still = NumberRange.new(0)
	local ringSize = 2 * LAYOUT.ringRadius / 0.62 * s -- the texture's bright line sits at 62% of its radius
	for _, a in ipairs({ aRingA, aRingB }) do
		make("ParticleEmitter", {
			Name = "EnergyRing",
			Texture = tex("EnergyRing"),
			Rate = 7,
			Lifetime = NumberRange.new(0.45, 0.6),
			Speed = still,
			LockedToPart = true,
			Rotation = NumberRange.new(0, 360),
			RotSpeed = NumberRange.new(-90, 90),
			Size = ns({ { 0, ringSize * 0.92 }, { 0.5, ringSize }, { 1, ringSize * 1.08 } }),
			Transparency = ns({ { 0, 1 }, { 0.3, 0.6 }, { 0.7, 0.68 }, { 1, 1 } }),
			LightEmission = 1,
			LightInfluence = 0,
			ZOffset = 0.3,
			Attributes = { TextureKey = "EnergyRing" },
		}, a)
	end
	-- the body of the figure-8 energy stream round both circles: a closed ring of curved beams
	-- (each attachment's X axis follows the path, so the beams join smoothly). StarburstVFX runs
	-- a wave of light round it and sends bright streams chasing along it.
	local nodes = LAYOUT.figure8Body -- closed: the last point repeats the first
	local ring = {}
	for i = 1, #nodes - 1 do
		local prev = nodes[i == 1 and #nodes - 1 or i - 1]
		local tangent = (toWorld(f, nodes[i + 1]) - toWorld(f, prev)).Unit
		local a = make("Attachment", { Name = "Figure8_" .. i }, shell)
		a.WorldCFrame = CFrame.fromMatrix(toWorld(f, nodes[i]), tangent, f.Y)
		ring[i] = a
	end
	for i, a0 in ipairs(ring) do
		local a1 = ring[i % #ring + 1]
		local handleLength = (a1.WorldPosition - a0.WorldPosition).Magnitude / 3
		make("Beam", {
			Name = "Figure8Body",
			Attachment0 = a0,
			Attachment1 = a1,
			Texture = tex("EnergyBand"),
			TextureMode = Enum.TextureMode.Stretch,
			Width0 = 0.14 * s,
			Width1 = 0.14 * s,
			CurveSize0 = handleLength,
			CurveSize1 = handleLength,
			Segments = 8,
			FaceCamera = true,
			LightEmission = 1,
			LightInfluence = 0,
			Transparency = NumberSequence.new(0.45),
			ZOffset = 0.28,
			Attributes = { TextureKey = "EnergyBand", Figure8 = i },
		}, shell)
	end
	local eye = LAYOUT.eyeRadius / 0.3 * s -- the Void texture is fully dark out to 30% of its radius
	make("ParticleEmitter", {
		Name = "EyeVoid",
		Texture = tex("Void"),
		Rate = 3,
		Lifetime = NumberRange.new(1.2),
		Speed = still,
		LockedToPart = true,
		Rotation = NumberRange.new(0, 360),
		RotSpeed = NumberRange.new(-20, 20),
		Size = ns({ { 0, eye * 0.95 }, { 0.5, eye }, { 1, eye * 0.95 } }),
		Transparency = ns({ { 0, 1 }, { 0.25, 0 }, { 0.75, 0 }, { 1, 1 } }),
		LightEmission = 0,
		LightInfluence = 0,
		ZOffset = 0.38, -- over the glow, so the eye stays dark
		Attributes = { TextureKey = "Void" },
	}, aRingA)
	make("ParticleEmitter", {
		Name = "RingCore",
		Texture = tex("HotCore"),
		Rate = 4,
		Lifetime = NumberRange.new(0.6),
		Speed = still,
		LockedToPart = true,
		Size = ns({ { 0, LAYOUT.ringRadius * 1.4 * s }, { 1, LAYOUT.ringRadius * 1.6 * s } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.55 }, { 0.7, 0.6 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.24,
		Attributes = { TextureKey = "HotCore" },
	}, aRingB)
	make("ParticleEmitter", {
		Name = "JunctionCore",
		Texture = tex("HotCore"),
		Rate = 10,
		Lifetime = NumberRange.new(0.3, 0.45),
		Speed = still,
		LockedToPart = true,
		Size = ns({ { 0, 0.22 * s }, { 0.5, 0.3 * s }, { 1, 0.25 * s } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.25 }, { 0.7, 0.35 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.35,
		Attributes = { TextureKey = "HotCore" },
	}, aJunction)
	make("ParticleEmitter", {
		Name = "Fragments",
		Texture = tex("Spark"),
		Orientation = Enum.ParticleOrientation.VelocityParallel,
		Rate = 9,
		Lifetime = NumberRange.new(0.25, 0.45),
		Speed = NumberRange.new(0.8 * s, 2.2 * s),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 4,
		Size = ns({ { 0, 0.07 * s }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.35,
		Attributes = { TextureKey = "Spark" },
	}, aJunction)
	-- an energy ring pulsing out of the circles now and then (more of them while charging)
	make("ParticleEmitter", {
		Name = "StarShimmer",
		Texture = tex("EnergyRing"),
		Rate = 0.6,
		Lifetime = NumberRange.new(0.6, 0.7),
		Speed = still,
		LockedToPart = true,
		Rotation = NumberRange.new(0, 360),
		Size = ns({ { 0, 0.3 * s }, { 1, 1.6 * s } }),
		Transparency = ns({ { 0, 0.2 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = 0.2,
		Attributes = { TextureKey = "EnergyRing" },
	}, aJunction)
	make("ParticleEmitter", {
		Name = "StarGlow",
		Texture = tex("Glow"),
		Rate = 4,
		Lifetime = NumberRange.new(0.6),
		Speed = still,
		LockedToPart = true,
		Size = ns({ { 0, 1.5 * s }, { 0.5, 1.75 * s }, { 1, 1.5 * s } }),
		Transparency = ns({ { 0, 1 }, { 0.3, 0.45 }, { 0.7, 0.45 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		ZOffset = -0.3,
		Attributes = { TextureKey = "Glow" },
	}, aJunction)
	make("PointLight", {
		Name = "StarLight",
		Range = 10 * s,
		Brightness = 2,
		Shadows = false,
		Attributes = { ColorKey = "Orange" },
	}, aStar)
	-- swing trails
	make("Trail", {
		Name = "SwingTrail",
		Attachment0 = aTrailBase,
		Attachment1 = aTip,
		Texture = tex("Trail"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.18,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 0.3,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "Trail", SwingTrail = true },
	}, fx)
	make("Trail", {
		Name = "SwingGlow",
		Attachment0 = aTrailBase,
		Attachment1 = aTip,
		Texture = tex("Glow"),
		TextureMode = Enum.TextureMode.Stretch,
		Lifetime = 0.26,
		MinLength = 0.05,
		Transparency = ns({ { 0, 0.55 }, { 1, 1 } }),
		LightEmission = 1,
		LightInfluence = 0,
		Enabled = false,
		Attributes = { TextureKey = "Glow", SwingTrail = true },
	}, fx)

	local sounds = Config.Sounds or {}
	for name, loudness in pairs({ Equip = 0.5, Swing = 0.6, Special = 0.8 }) do
		make("Sound", { Name = name .. "Sound", SoundId = sounds[name] or "", Volume = loudness }, handle)
	end

	for _, m in ipairs(f.markers) do
		m:Destroy()
	end
	swordModel:Destroy()

	tool.Parent = StarterPack
	local copy = tool:Clone()
	copy.Parent = ServerStorage
	local okVfx, VFX = pcall(require, folder:FindFirstChild("StarburstVFX"))
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
		note("StarburstSword not found, so only the scripts were updated (the existing sword was kept)")
	else
		note("StarburstSword not found: import StarburstSword.fbx (or .glb) with the 3D Importer, then run this again")
	end
end

if recording then
	pcall(function()
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end)
end

print(("[Starburst] Install finished%s. Sword: %s | Scripts: ReplicatedStorage.StarburstSword, "):format(
	#notes > 0 and (" with " .. #notes .. " note(s) above") or "",
	tool and tool:GetFullName() or "not built"
) .. "ServerScriptService.StarburstServer, StarterPlayerScripts.StarburstClient")
