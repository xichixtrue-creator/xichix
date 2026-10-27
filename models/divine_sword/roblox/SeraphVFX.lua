-- Seraph Blade effects. Lives in ReplicatedStorage.SeraphBlade.SeraphVFX.
-- Clients play everything; the server only calls ApplyColors / ComputeImpact.
-- The always-on aura (energy ribbons, white and gold glow, halo, light rays, sparkles, motes)
-- is built by the installer; this module adds the moving parts (streams of light racing along
-- the ribbons, the guard light's pulse) and the attack effects.

local Debris = game:GetService("Debris")
local Lighting = game:GetService("Lighting")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local Workspace = game:GetService("Workspace")

local Folder = script.Parent
local Config = require(Folder:WaitForChild("Config"))
local Layout = require(Folder:WaitForChild("Layout"))

local VFX = {}

-- Config.VFX value with a default, so a Config kept from an older install still works.
local function opt(key, default)
	local v = Config.VFX[key]
	if v == nil then
		return default
	end
	return v
end

-- ---------------------------------------------------------------- lookups

local function assets()
	return Folder:FindFirstChild("Assets")
end

-- Texture id for a key, and true when it had to fall back to a built-in texture.
function VFX.Texture(key)
	local override = Config.Textures[key]
	if override and override ~= "" then
		return override, false
	end
	local a = assets()
	local id = a and a:GetAttribute("Tex_" .. key)
	if typeof(id) == "string" and id ~= "" then
		return id, false
	end
	return Config.FallbackTextures[key] or Config.FallbackTextures.Default, true
end

-- "Light" = glowing Neon, "Glass" = clear crystal, "Texture" = opaque with the painted facets.
local function applyStyle(part, style, transparency)
	local texture = part:GetAttribute("CrystalTexture") or ""
	if style == "Light" then
		part.Material = Enum.Material.Neon
		part.TextureID = ""
		part.Transparency = transparency
	elseif style == "Texture" then
		part.Material = Enum.Material.SmoothPlastic
		part.TextureID = texture
		part.Transparency = 0
	else
		part.Material = Enum.Material.Glass
		part.TextureID = texture
		part.Transparency = transparency
	end
end

-- Applies Config.Colors and the crystal / gem styles to the sword's parts and refreshes every
-- emitter / beam / trail tagged with a TextureKey attribute.
function VFX.ApplyColors(tool)
	local auraOn = opt("Aura", true)
	for _, inst in ipairs(tool:GetDescendants()) do
		local colorKey = inst:GetAttribute("ColorKey")
		if colorKey and Config.Colors[colorKey] and (inst:IsA("BasePart") or inst:IsA("Light")) then
			inst.Color = Config.Colors[colorKey]
		end
		if inst:IsA("MeshPart") and inst:GetAttribute("Crystal") then
			applyStyle(inst, Config.CrystalStyle or "Light", Config.CrystalTransparency or 0.08)
		elseif inst:IsA("MeshPart") and inst:GetAttribute("Gem") then
			applyStyle(inst, Config.GemStyle or "Glass", 0.15)
		end
		if inst:IsA("Beam") and inst:GetAttribute("Aura") then
			inst.Enabled = auraOn
		end
		local key = inst:GetAttribute("TextureKey")
		if key and (inst:IsA("ParticleEmitter") or inst:IsA("Trail") or inst:IsA("Beam")) then
			local id, fallback = VFX.Texture(key)
			inst.Texture = id
			if inst:IsA("ParticleEmitter") and inst:GetAttribute("Flipbook") then
				inst.FlipbookLayout = fallback and Enum.ParticleFlipbookLayout.None or Enum.ParticleFlipbookLayout.Grid4x4
			end
		end
	end
end

-- Where Heaven's Verdict lands: the ground under the attacker.
function VFX.ComputeImpact(character)
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return Vector3.zero
	end
	local ignore = { character }
	local fx = Workspace:FindFirstChild("SeraphBladeFX")
	if fx then
		table.insert(ignore, fx)
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = ignore
	local hit = Workspace:Raycast(root.Position, Vector3.new(0, -12, 0), params)
	return hit and hit.Position or (root.Position - Vector3.new(0, 3, 0))
end

-- ---------------------------------------------------------------- helpers

local function ns(points)
	local keys = {}
	for _, p in ipairs(points) do
		table.insert(keys, NumberSequenceKeypoint.new(p[1], p[2]))
	end
	return NumberSequence.new(keys)
end

local function fxFolder()
	local f = Workspace:FindFirstChild("SeraphBladeFX")
	if not f then
		f = Instance.new("Folder")
		f.Name = "SeraphBladeFX"
		f.Parent = Workspace
	end
	return f
end

local function animate(duration, step)
	local start = os.clock()
	local conn
	conn = RunService.RenderStepped:Connect(function()
		local t = math.min(1, (os.clock() - start) / duration)
		local ok = pcall(step, t)
		if t >= 1 or not ok then
			conn:Disconnect()
		end
	end)
end

local function easeOut(t)
	return 1 - (1 - t) ^ 3
end

local function worldAttachment(position)
	local a = Instance.new("Attachment")
	a.Parent = Workspace.Terrain
	a.WorldPosition = position
	return a
end

local function newEmitter(parent, props)
	local e = Instance.new("ParticleEmitter")
	e.Enabled = false
	e.LightInfluence = 0
	e.Speed = NumberRange.new(0)
	for k, v in pairs(props) do
		e[k] = v
	end
	e.Parent = parent
	return e
end

local function newBeam(a0, a1, props)
	local b = Instance.new("Beam")
	b.Attachment0 = a0
	b.Attachment1 = a1
	b.FaceCamera = true
	b.LightInfluence = 0
	b.Segments = 1
	b.TextureMode = Enum.TextureMode.Stretch
	for k, v in pairs(props) do
		b[k] = v
	end
	b.Parent = fxFolder()
	return b
end

local function emit(tool, name, count)
	for _, d in ipairs(tool:GetDescendants()) do
		if d.Name == name and d:IsA("ParticleEmitter") then
			d:Emit(count)
		end
	end
end

local function playSound(tool, name)
	local handle = tool:FindFirstChild("Handle")
	local sound = handle and handle:FindFirstChild(name)
	if sound and sound:IsA("Sound") and sound.SoundId ~= "" then
		sound:Play()
	end
end

local trailTokens = setmetatable({}, { __mode = "k" })

local function flashTrails(tool, duration)
	for _, d in ipairs(tool:GetDescendants()) do
		if d:IsA("Trail") and d:GetAttribute("SwingTrail") then
			local token = (trailTokens[d] or 0) + 1
			trailTokens[d] = token
			d.Enabled = true
			task.delay(duration, function()
				if trailTokens[d] == token and d.Parent then
					d.Enabled = false
				end
			end)
		end
	end
end

local function gemAttachment(tool)
	local handle = tool:FindFirstChild("Handle")
	return handle and handle:FindFirstChild("Gem")
end

local function gemLight(tool)
	local gem = gemAttachment(tool)
	return gem and gem:FindFirstChild("GemLight")
end

local function pulseLight(tool, brightness, duration)
	local light = gemLight(tool)
	if not light then
		return
	end
	local base = light:GetAttribute("BaseBrightness") or light.Brightness
	light:SetAttribute("BaseBrightness", base)
	light:SetAttribute("BoostUntil", os.clock() + duration) -- the idle pulse waits for this
	light.Brightness = brightness
	TweenService:Create(light, TweenInfo.new(duration, Enum.EasingStyle.Quad), { Brightness = base }):Play()
end

local function boostRates(tool, factor, duration)
	for _, d in ipairs(tool:GetDescendants()) do
		if d:IsA("ParticleEmitter") and (d:GetAttribute("BaseRate") or d.Rate) > 0 then
			local base = d:GetAttribute("BaseRate") or d.Rate
			d:SetAttribute("BaseRate", base)
			d.Rate = base * factor
			task.delay(duration, function()
				if d.Parent then
					d.Rate = base
				end
			end)
		end
	end
end

-- The sword's own frame: the "Origin" attachment sits at the Blender origin (the guard gem's
-- centre); its X is Blender X, its Y runs up towards the pommel.
local function originAttachment(tool)
	local handle = tool:FindFirstChild("Handle")
	return handle and handle:FindFirstChild("Origin")
end

local function layoutToLocal(origin, p, scale)
	return origin.CFrame * (Vector3.new(p[1], p[3], -p[2]) * scale)
end

-- ---------------------------------------------------------------- building blocks

-- A white-gold crescent slash built from short camera-facing beam segments.
local SEGMENTS = 12

local function crescent(character, roll, radius, width, duration, sweep)
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	local rcf = root.CFrame
	local base = CFrame.fromMatrix(rcf.Position + Vector3.new(0, 0.8, 0), rcf.RightVector, rcf.LookVector)
		* CFrame.Angles(0, math.rad(roll), 0)
	local atts, beams = {}, {}
	for i = 0, SEGMENTS do
		atts[i] = worldAttachment(rcf.Position)
	end
	local tex = VFX.Texture("SlashBand")
	local function widthAt(f)
		return width * math.sin(math.pi * f) ^ 0.7 * (0.35 + 0.65 * f) + 0.04
	end
	for i = 1, SEGMENTS do
		beams[i] = newBeam(atts[i - 1], atts[i], {
			Texture = tex,
			LightEmission = 0.6,
			Width0 = widthAt((i - 1) / SEGMENTS),
			Width1 = widthAt(i / SEGMENTS),
			ZOffset = 0.5,
		})
	end
	sweep = sweep or 210
	animate(duration, function(t)
		local e = easeOut(t)
		local frame = base * CFrame.Angles(0, 0, math.rad(40 - 60 * e))
		local r = radius * (0.8 + 0.3 * e)
		for i = 0, SEGMENTS do
			local th = math.rad(-sweep / 2 + sweep * i / SEGMENTS)
			atts[i].WorldPosition = frame:PointToWorldSpace(Vector3.new(r * math.sin(th), r * math.cos(th), 0))
		end
		local fade = NumberSequence.new(math.clamp(t ^ 1.5, 0, 1))
		for _, b in ipairs(beams) do
			b.Transparency = fade
		end
	end)
	for i = 0, SEGMENTS do
		Debris:AddItem(atts[i], duration + 0.1)
	end
	for _, b in ipairs(beams) do
		Debris:AddItem(b, duration + 0.1)
	end
end

-- A spinning ring of white-gold light round a point (Heaven's Verdict).
local function energyRing(centre, radius, width, duration, spin)
	local n = 16
	local atts, beams = {}, {}
	for i = 0, n do
		atts[i] = worldAttachment(centre)
	end
	local tex = VFX.Texture("SlashBand")
	for i = 1, n do
		beams[i] = newBeam(atts[i - 1], atts[i], {
			Texture = tex,
			LightEmission = 0.7,
			Width0 = width,
			Width1 = width,
			ZOffset = 0.6,
		})
	end
	animate(duration, function(t)
		local e = easeOut(t)
		local r = radius * (0.25 + 0.75 * e)
		local a0 = spin * e
		for i = 0, n do
			local th = a0 + 2 * math.pi * i / n
			atts[i].WorldPosition = centre + Vector3.new(math.cos(th) * r, 0.15 * math.sin(th * 3 + t * 8), math.sin(th) * r)
		end
		local fade = NumberSequence.new(math.clamp((t - 0.35) / 0.65, 0, 1))
		for _, b in ipairs(beams) do
			b.Transparency = fade
		end
	end)
	for i = 0, n do
		Debris:AddItem(atts[i], duration + 0.1)
	end
	for _, b in ipairs(beams) do
		Debris:AddItem(b, duration + 0.1)
	end
end

-- A burst of divine light: a white flash, soft rays, star flashes and drifting motes.
local function burstAt(position, scale, opts)
	local att = worldAttachment(position)
	newEmitter(att, {
		Texture = VFX.Texture("GlowWhite"),
		Lifetime = NumberRange.new(0.25),
		Size = ns({ { 0, scale * 0.8 }, { 1, scale * 1.9 } }),
		Transparency = ns({ { 0, 0.1 }, { 1, 1 } }),
		LightEmission = 1,
		ZOffset = 1,
	}):Emit(1)
	newEmitter(att, {
		Texture = VFX.Texture("Rays"),
		Lifetime = NumberRange.new(0.35),
		Rotation = NumberRange.new(0, 360),
		RotSpeed = NumberRange.new(-60, 60),
		Size = ns({ { 0, scale * 0.6 }, { 1, scale * 2.2 } }),
		Transparency = ns({ { 0, 0.2 }, { 1, 1 } }),
		LightEmission = 1,
		ZOffset = 0.9,
	}):Emit(1)
	newEmitter(att, {
		Texture = VFX.Texture("Sparkle"),
		Lifetime = NumberRange.new(0.3, 0.6),
		Speed = NumberRange.new(5 * scale / 3, 12 * scale / 3),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 4,
		Rotation = NumberRange.new(0, 45),
		Size = ns({ { 0, 0.4 }, { 1, 0 } }),
		LightEmission = 1,
	}):Emit(opts.sparkles)
	newEmitter(att, {
		Texture = VFX.Texture("Mote"),
		Lifetime = NumberRange.new(0.6, 1.2),
		Speed = NumberRange.new(1, 4),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 2,
		Acceleration = Vector3.new(0, 1.5, 0),
		Size = ns({ { 0, 0.14 }, { 1, 0 } }),
		LightEmission = 1,
	}):Emit(opts.motes)
	local light = Instance.new("PointLight")
	light.Color = Config.Colors.Light
	light.Range = opts.lightRange
	light.Brightness = opts.light
	light.Shadows = false
	light.Parent = att
	TweenService:Create(light, TweenInfo.new(0.45, Enum.EasingStyle.Quad), { Brightness = 0 }):Play()
	if Config.Sounds.Impact ~= "" then
		local s = Instance.new("Sound")
		s.SoundId = Config.Sounds.Impact
		s.Volume = 0.7
		s.Parent = att
		s:Play()
	end
	Debris:AddItem(att, 1.6)
end

-- The holy circle that opens on the ground under Heaven's Verdict.
local function groundCircle(position, size, duration)
	local p = Instance.new("Part")
	p.Name = "VerdictCircle"
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.Transparency = 1
	p.Size = Vector3.new(1, 0.05, 1)
	p.CFrame = CFrame.new(position + Vector3.new(0, 0.06, 0))
	p.Parent = fxFolder()
	local decal = Instance.new("Decal")
	decal.Face = Enum.NormalId.Top
	decal.Texture = VFX.Texture("HolyCircle")
	decal.Color3 = Color3.new(1, 1, 1)
	decal.Parent = p
	animate(duration, function(t)
		local s = size * (0.3 + 0.7 * easeOut(math.min(1, t * 2.5)))
		p.Size = Vector3.new(s, 0.05, s)
		decal.Transparency = math.clamp((t - 0.4) / 0.6, 0, 1)
	end)
	Debris:AddItem(p, duration + 0.1)
end

local function screenFlash()
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "SeraphFlash"
	cc.Brightness = 0.18
	cc.Contrast = 0.1
	cc.Saturation = 0.1
	cc.TintColor = Color3.fromRGB(255, 246, 225)
	cc.Parent = Lighting
	TweenService:Create(cc, TweenInfo.new(0.4, Enum.EasingStyle.Quad), {
		Brightness = 0,
		Contrast = 0,
		Saturation = 0,
		TintColor = Color3.new(1, 1, 1),
	}):Play()
	Debris:AddItem(cc, 0.45)
end

local shakeCount = 0

local function cameraShake(intensity, duration)
	shakeCount += 1
	local name = "SeraphShake" .. shakeCount
	local start = os.clock()
	RunService:BindToRenderStep(name, Enum.RenderPriority.Camera.Value + 1, function()
		local t = (os.clock() - start) / duration
		local cam = Workspace.CurrentCamera
		if t >= 1 or not cam then
			RunService:UnbindFromRenderStep(name)
			return
		end
		local a = intensity * (1 - t) ^ 2
		cam.CFrame = cam.CFrame
			* CFrame.Angles(math.rad((math.random() - 0.5) * a), math.rad((math.random() - 0.5) * a), 0)
	end)
end

-- ---------------------------------------------------------------- attacks

function VFX.Swing(tool, combo)
	local character = tool.Parent
	if not (character and character:IsA("Model")) then
		return
	end
	flashTrails(tool, 0.35)
	emit(tool, "SwingSparkles", combo == 3 and 16 or 10)
	playSound(tool, "SwingSound")
	pulseLight(tool, 4, 0.3)
	local roll = Config.SlashAngles[combo] or 70
	local radius = opt("SlashRadius", 5) * (combo == 3 and 1.15 or 1)
	task.delay(0.05, function()
		crescent(character, roll, radius, opt("SlashWidth", 1.2), 0.24)
	end)
end

function VFX.SpecialCharge(tool)
	local windup = Config.Combat.SpecialWindup
	local head = gemAttachment(tool)
	if head then
		newEmitter(head, {
			Texture = VFX.Texture("GlowWhite"),
			LockedToPart = true,
			Lifetime = NumberRange.new(windup + 0.15),
			Size = ns({ { 0, 0.5 }, { 1, 3 } }),
			Transparency = ns({ { 0, 0.4 }, { 0.8, 0.1 }, { 1, 1 } }),
			LightEmission = 1,
			ZOffset = 0.6,
		}):Emit(1)
	end
	if head then
		-- a halo of light closing in on the guard gem as the Verdict charges
		newEmitter(head, {
			Texture = VFX.Texture("Halo"),
			LockedToPart = true,
			Lifetime = NumberRange.new(windup),
			Size = ns({ { 0, 3.2 }, { 1, 0.5 } }),
			Transparency = ns({ { 0, 1 }, { 0.3, 0.15 }, { 1, 0.5 } }),
			LightEmission = 1,
			ZOffset = 0.7,
		}):Emit(1)
	end
	boostRates(tool, 3, windup + 0.3)
	pulseLight(tool, 6, windup + 0.4)
	flashTrails(tool, windup + 0.5)
end

function VFX.SpecialRelease(tool, impact, isLocalAttacker)
	local character = tool.Parent
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	impact = impact or VFX.ComputeImpact(character)
	playSound(tool, "SpecialSound")
	local radius = opt("VerdictRadius", 11)
	local waist = Vector3.new(impact.X, root.Position.Y, impact.Z)
	-- Heaven's Verdict: a pillar of light strikes down on you, a holy circle opens on the
	-- ground and rings of white-gold light burst out all the way round
	local top, bottom = worldAttachment(impact + Vector3.new(0, 40, 0)), worldAttachment(impact)
	local pillar = newBeam(top, bottom, {
		Texture = VFX.Texture("Pillar"),
		TextureMode = Enum.TextureMode.Stretch,
		LightEmission = 1,
		Width0 = 4,
		Width1 = 4,
		ZOffset = 0.5,
	})
	animate(0.7, function(t)
		local w = 4.5 * (1 - t) ^ 0.6 + 0.3
		pillar.Width0, pillar.Width1 = w, w
		pillar.Transparency = NumberSequence.new(math.clamp((t - 0.3) / 0.7, 0, 1))
	end)
	for _, inst in ipairs({ top, bottom, pillar }) do
		Debris:AddItem(inst, 0.8)
	end
	energyRing(waist + Vector3.new(0, 0.3, 0), radius, 1.6, 0.55, math.pi)
	task.delay(0.08, function()
		energyRing(impact + Vector3.new(0, 0.4, 0), radius * 0.85, 1.0, 0.5, -math.pi)
	end)
	groundCircle(impact, radius * 2, 1.4)
	burstAt(root.Position + Vector3.new(0, 1, 0), 4, { sparkles = 30, motes = 30, light = 7, lightRange = 18 })
	emit(tool, "SwingSparkles", 20)
	for k = 0, 5 do
		local a = 2 * math.pi * k / 6
		task.delay(0.05 * k, function()
			burstAt(waist + Vector3.new(math.cos(a), 0, math.sin(a)) * radius * 0.65, 2.5,
				{ sparkles = 8, motes = 8, light = 2, lightRange = 8 })
		end)
	end
	local cam = Workspace.CurrentCamera
	if opt("ScreenFlash", true) and cam and (cam.CFrame.Position - impact).Magnitude < 70 then
		screenFlash()
	end
	if isLocalAttacker and opt("CameraShake", true) then
		cameraShake(1.4, 0.3)
	end
end

function VFX.Impact(position, isSpecial)
	local scale = isSpecial and 3.6 or 2.4
	burstAt(position, scale, {
		sparkles = isSpecial and 18 or 10,
		motes = isSpecial and 14 or 8,
		light = isSpecial and 5 or 3,
		lightRange = isSpecial and 14 or 9,
	})
end

-- ---------------------------------------------------------------- idle: the moving aura

local idle = {}

-- Point along a polyline at fraction s (0..1).
local function along(path, lengths, total, s)
	local target = s * total
	for i = 1, #lengths do
		if target <= lengths[i] or i == #lengths then
			local f = lengths[i] > 0 and math.clamp(target / lengths[i], 0, 1) or 0
			local a, b = path[i], path[i + 1]
			return a:Lerp(b, f), (b - a)
		end
		target -= lengths[i]
	end
	return path[#path], Vector3.zero
end

function VFX.StartIdle(tool)
	if idle[tool] then
		return
	end
	local handle = tool:FindFirstChild("Handle")
	local origin = originAttachment(tool)
	if not (handle and origin) then
		return
	end
	local scale = tool:GetAttribute("SeraphScale") or 1
	local state = { streams = {} }
	-- bright streams of light racing along the ribbons from the tip up to the guard
	local ribbons = Layout.Ribbons or {}
	local count = opt("Aura", true) and math.max(0, math.floor(opt("Streams", 2))) or 0
	for i = 1, count do
		local raw = ribbons[(i - 1) % math.max(1, #ribbons) + 1]
		if raw and #raw > 1 then
			local path, lengths, total = {}, {}, 0
			for _, p in ipairs(raw) do
				table.insert(path, layoutToLocal(origin, p, scale))
			end
			for k = 1, #path - 1 do
				lengths[k] = (path[k + 1] - path[k]).Magnitude
				total += lengths[k]
			end
			local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
			a0.Name, a1.Name = "Stream" .. i .. "A", "Stream" .. i .. "B"
			a0.Parent, a1.Parent = handle, handle
			local trail = Instance.new("Trail")
			trail.Attachment0, trail.Attachment1 = a0, a1
			trail.Texture = VFX.Texture("Trail")
			trail.TextureMode = Enum.TextureMode.Stretch
			trail.Lifetime = opt("StreamLifetime", 0.35)
			trail.MinLength = 0.02
			trail.FaceCamera = true
			trail.LightEmission = 1
			trail.LightInfluence = 0
			trail.WidthScale = ns({ { 0, 1 }, { 1, 0.15 } })
			trail.Transparency = ns({ { 0, 0 }, { 1, 1 } })
			trail.Enabled = false
			trail.Parent = handle
			table.insert(state.streams, {
				a0 = a0,
				a1 = a1,
				trail = trail,
				path = path,
				lengths = lengths,
				total = total,
				phase = (i - 1) / count,
				last = 0,
			})
		end
	end
	state.conn = RunService.RenderStepped:Connect(function()
		if not (tool.Parent and handle.Parent) then
			VFX.StopIdle(tool)
			return
		end
		local now = os.clock()
		local cam = Workspace.CurrentCamera
		local near = cam ~= nil and (cam.CFrame.Position - handle.Position).Magnitude < opt("IdleRange", 140)
		local normal = origin.CFrame.LookVector
		local speed = opt("StreamSpeed", 0.35)
		for _, st in ipairs(state.streams) do
			-- race along the ribbon, pause, start again at the tip
			local s = (now * speed + st.phase) % 1.3
			local drawing = near and s <= 1
			if drawing then
				local pos, dir = along(st.path, st.lengths, st.total, s)
				local side = dir.Magnitude > 1e-4 and dir.Unit:Cross(normal) or Vector3.xAxis
				local w = 0.07 * scale * math.sin(math.pi * math.min(1, s * 1.05)) ^ 0.5
				st.a0.Position = pos - side * w * 0.5
				st.a1.Position = pos + side * w * 0.5
			end
			-- jumping back to the tip with the trail on would draw a line up the blade
			st.trail.Enabled = drawing and s >= st.last
			st.last = s
		end
		if near and opt("HaloPulse", true) then
			local light = gemLight(tool)
			if light and now > (light:GetAttribute("BoostUntil") or 0) then
				local base = light:GetAttribute("BaseBrightness") or light.Brightness
				light:SetAttribute("BaseBrightness", base)
				light.Brightness = base * (0.85 + 0.15 * math.sin(now * 2.2))
			end
		end
	end)
	idle[tool] = state
end

function VFX.StopIdle(tool)
	local state = idle[tool]
	if not state then
		return
	end
	idle[tool] = nil
	if state.conn then
		state.conn:Disconnect()
	end
	for _, st in ipairs(state.streams) do
		st.trail:Destroy()
		st.a0:Destroy()
		st.a1:Destroy()
	end
end

return VFX
