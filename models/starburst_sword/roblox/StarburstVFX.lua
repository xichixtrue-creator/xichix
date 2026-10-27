-- Starburst Blade effects. Lives in ReplicatedStorage.StarburstSword.StarburstVFX.
-- Clients play everything; the server only calls ApplyColors / ComputeImpact.
-- The sword itself is drawn by additive energy layers (LightEmission 1); the attack
-- textures are pre-coloured (fire with dark outlines, like the reference sheet), so those
-- effects use a white tint and low LightEmission to keep the outlines dark.

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

-- Applies Config.Colors (and the mesh transparency) to parts tagged with a ColorKey
-- attribute and refreshes every emitter / beam / trail tagged with a TextureKey attribute.
function VFX.ApplyColors(tool)
	local meshTransparency = opt("MeshTransparency", 0.8)
	for _, inst in ipairs(tool:GetDescendants()) do
		local colorKey = inst:GetAttribute("ColorKey")
		if colorKey and Config.Colors[colorKey] and (inst:IsA("BasePart") or inst:IsA("Light")) then
			inst.Color = Config.Colors[colorKey]
		end
		if colorKey and colorKey ~= "Aura" and inst:IsA("BasePart") then
			inst.Transparency = meshTransparency
		end
		if inst:IsA("Beam") and inst:GetAttribute("Figure8") then
			inst.Enabled = opt("Figure8", true)
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

function VFX.ComputeImpact(character)
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return Vector3.zero
	end
	local ahead = root.Position + root.CFrame.LookVector * (Config.Combat.SpecialRange * 0.55)
	local ignore = { character }
	local fx = Workspace:FindFirstChild("StarburstFX")
	if fx then
		table.insert(ignore, fx)
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = ignore
	local hit = Workspace:Raycast(ahead + Vector3.new(0, 4, 0), Vector3.new(0, -14, 0), params)
	return hit and hit.Position or (ahead - Vector3.new(0, 2.8, 0))
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
	local f = Workspace:FindFirstChild("StarburstFX")
	if not f then
		f = Instance.new("Folder")
		f.Name = "StarburstFX"
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

local function pulseLight(tool, brightness, duration)
	local shell = tool:FindFirstChild("Shell")
	local star = shell and shell:FindFirstChild("Star")
	local light = star and star:FindFirstChild("StarLight")
	if not light then
		return
	end
	local base = light:GetAttribute("BaseBrightness") or light.Brightness
	light:SetAttribute("BaseBrightness", base)
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

-- The sword's own frame: the "Star" attachment's X is across the blade, Y up the blade.
-- Layout points are Blender coordinates (x, depth, up) relative to the star.
local function starAttachment(tool)
	local shell = tool:FindFirstChild("Shell")
	return shell and shell:FindFirstChild("Star")
end

local function layoutToLocal(star, p, scale)
	return star.CFrame * (Vector3.new(p[1], p[3], -p[2]) * scale)
end

-- ---------------------------------------------------------------- building blocks

-- A painted crescent slash built from short camera-facing beam segments.
local SEGMENTS = 10

local function crescent(character, roll, radius, width, duration, travel)
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	local rcf = root.CFrame
	local base = CFrame.fromMatrix(rcf.Position + Vector3.new(0, 0.7, 0), rcf.RightVector, rcf.LookVector)
		* CFrame.Angles(0, math.rad(roll), 0)
	local atts, beams = {}, {}
	for i = 0, SEGMENTS do
		atts[i] = worldAttachment(rcf.Position)
	end
	local tex = VFX.Texture("SlashStrip")
	local function widthAt(f)
		return width * math.sin(math.pi * f) ^ 0.8 * (0.4 + 0.6 * f) + 0.03
	end
	for i = 1, SEGMENTS do
		beams[i] = newBeam(atts[i - 1], atts[i], {
			Texture = tex,
			LightEmission = 0.35,
			Width0 = widthAt((i - 1) / SEGMENTS),
			Width1 = widthAt(i / SEGMENTS),
			ZOffset = 0.5,
		})
	end
	animate(duration, function(t)
		local e = easeOut(t)
		-- sweep around the centre so the thick head leads the swing
		local frame = base * CFrame.new(0, (travel or 0) * e, 0) * CFrame.Angles(0, 0, math.rad(35 - 50 * e))
		local r = radius * (0.8 + 0.3 * e)
		for i = 0, SEGMENTS do
			local th = math.rad(-105 + 210 * i / SEGMENTS)
			atts[i].WorldPosition = frame:PointToWorldSpace(Vector3.new(r * math.sin(th), r * math.cos(th), 0))
		end
		local fade = NumberSequence.new(math.clamp(t ^ 1.6, 0, 1))
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

-- Sheet item 1: a streak that flies out and ends in a bright flare.
local function dart(from, dir, length, travel, life, width)
	local tail, head = worldAttachment(from), worldAttachment(from)
	local beam = newBeam(tail, head, {
		Texture = VFX.Texture("Dart"),
		LightEmission = 0.4,
		Width0 = width * 0.25,
		Width1 = width,
		ZOffset = 0.3,
	})
	animate(life, function(t)
		local e = easeOut(t)
		local h = from + dir * travel * e - Vector3.new(0, 1.5 * t * t, 0)
		head.WorldPosition = h
		tail.WorldPosition = h - dir * length * (1 - 0.6 * t)
		beam.Transparency = NumberSequence.new(t ^ 2)
	end)
	for _, inst in ipairs({ tail, head, beam }) do
		Debris:AddItem(inst, life + 0.1)
	end
end

local function randomDir()
	local d = Vector3.new(math.random() - 0.5, math.random() - 0.3, math.random() - 0.5)
	return d.Magnitude > 1e-3 and d.Unit or Vector3.yAxis
end

-- Sheet item 3 star: dark-eyed starburst, a hot flash, sparks and embers.
local function burstAt(position, scale, opts)
	local att = worldAttachment(position)
	newEmitter(att, {
		Texture = VFX.Texture("Starburst"),
		Lifetime = NumberRange.new(0.26, 0.32),
		Rotation = NumberRange.new(0, 360),
		Size = ns({ { 0, scale * 0.55 }, { 0.25, scale }, { 1, scale * 1.12 } }),
		Transparency = ns({ { 0, 0 }, { 0.6, 0.1 }, { 1, 1 } }),
		LightEmission = 0.25,
		ZOffset = 1,
	}):Emit(1)
	newEmitter(att, {
		Texture = VFX.Texture("Glow"),
		Lifetime = NumberRange.new(0.18),
		Size = ns({ { 0, scale * 1.2 }, { 1, scale * 2 } }),
		Transparency = ns({ { 0, 0.15 }, { 1, 1 } }),
		LightEmission = 1,
	}):Emit(1)
	newEmitter(att, {
		Texture = VFX.Texture("Spark"),
		Orientation = Enum.ParticleOrientation.VelocityParallel,
		Lifetime = NumberRange.new(0.25, 0.5),
		Speed = NumberRange.new(14, 26),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 4,
		Acceleration = Vector3.new(0, -12, 0),
		Size = ns({ { 0, 0.32 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 1, 1 } }),
		LightEmission = 0.6,
	}):Emit(opts.sparks)
	newEmitter(att, {
		Texture = VFX.Texture("Ember"),
		Lifetime = NumberRange.new(0.5, 1.0),
		Speed = NumberRange.new(3, 9),
		SpreadAngle = Vector2.new(180, 180),
		Drag = 2,
		Acceleration = Vector3.new(0, 3, 0),
		Size = ns({ { 0, 0.18 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0 }, { 0.7, 0.2 }, { 1, 1 } }),
		LightEmission = 0.8,
	}):Emit(opts.embers)
	local light = Instance.new("PointLight")
	light.Color = Config.Colors.Orange
	light.Range = opts.lightRange
	light.Brightness = opts.light
	light.Shadows = false
	light.Parent = att
	TweenService:Create(light, TweenInfo.new(0.4, Enum.EasingStyle.Quad), { Brightness = 0 }):Play()
	if Config.Sounds.Impact ~= "" then
		local s = Instance.new("Sound")
		s.SoundId = Config.Sounds.Impact
		s.Volume = 0.7
		s.Parent = att
		s:Play()
	end
	for _ = 1, opts.darts do
		dart(position, randomDir(), 0.9 * scale / 3, 2.2 * scale, 0.32, 0.12 * scale + 0.1)
	end
	Debris:AddItem(att, 1.5)
end

-- Sheet item 4: a dark starry portal with a fiery rim and a spinning swirl.
local function portal(position, size, life)
	local att = worldAttachment(position)
	newEmitter(att, {
		Texture = VFX.Texture("Portal"),
		Lifetime = NumberRange.new(life),
		Size = ns({ { 0, 0 }, { 0.3, size }, { 0.8, size * 1.08 }, { 1, 0 } }),
		Transparency = ns({ { 0, 0.1 }, { 1, 0.1 } }),
		LightEmission = 0,
		ZOffset = -2,
	}):Emit(1)
	newEmitter(att, {
		Texture = VFX.Texture("Swirl"),
		Lifetime = NumberRange.new(life * 0.9),
		Size = ns({ { 0, 0 }, { 0.3, size * 1.15 }, { 1, size * 1.4 } }),
		RotSpeed = NumberRange.new(250),
		Transparency = ns({ { 0, 0 }, { 0.7, 0.2 }, { 1, 1 } }),
		LightEmission = 0.35,
		ZOffset = -1,
	}):Emit(1)
	Debris:AddItem(att, life + 0.5)
end

-- Sheet item 2: a patch of flame licks on the ground.
local function firePatch(position, radius, duration)
	local p = Instance.new("Part")
	p.Name = "FirePatch"
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.Transparency = 1
	p.Size = Vector3.new(radius * 2, 0.2, radius * 2)
	p.CFrame = CFrame.new(position + Vector3.new(0, 0.2, 0))
	p.Parent = fxFolder()
	local flames = newEmitter(p, {
		Texture = VFX.Texture("FireLick"),
		FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4,
		FlipbookMode = Enum.ParticleFlipbookMode.OneShot,
		Shape = Enum.ParticleEmitterShape.Box,
		ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
		Rate = 70,
		Lifetime = NumberRange.new(0.45, 0.75),
		Speed = NumberRange.new(0.5, 1.5),
		Acceleration = Vector3.new(0, 3, 0),
		Size = ns({ { 0, 0.9 }, { 1, 1.4 } }),
		LightEmission = 0.3,
		ZOffset = 0.2,
	})
	if select(2, VFX.Texture("FireLick")) then
		flames.FlipbookLayout = Enum.ParticleFlipbookLayout.None
	end
	flames.Enabled = true
	task.delay(duration, function()
		flames.Enabled = false
	end)
	Debris:AddItem(p, duration + 1.2)
end

local function screenFlash()
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "StarburstFlash"
	cc.Brightness = 0.25
	cc.Contrast = 0.15
	cc.Saturation = 0.25
	cc.TintColor = Color3.fromRGB(255, 214, 170)
	cc.Parent = Lighting
	TweenService:Create(cc, TweenInfo.new(0.35, Enum.EasingStyle.Quad), {
		Brightness = 0,
		Contrast = 0,
		Saturation = 0,
		TintColor = Color3.new(1, 1, 1),
	}):Play()
	Debris:AddItem(cc, 0.4)
end

local shakeCount = 0

local function cameraShake(intensity, duration)
	shakeCount += 1
	local name = "StarburstShake" .. shakeCount
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
	flashTrails(tool, 0.3)
	emit(tool, "SwingSparks", 16)
	playSound(tool, "SwingSound")
	pulseLight(tool, 4, 0.25)
	local roll = Config.SlashAngles[combo] or 70
	local radius = Config.VFX.SlashRadius * (combo == 3 and 1.15 or 1)
	task.delay(0.05, function()
		crescent(character, roll, radius, Config.VFX.SlashWidth, 0.22, 0.6)
	end)
	local fx = tool:FindFirstChild("FXBlade")
	local tip = fx and fx:FindFirstChild("BladeTip")
	if tip then
		task.delay(0.08, function()
			for _ = 1, 3 do
				dart(tip.WorldPosition, randomDir(), 0.7, 5, 0.3, 0.22)
			end
		end)
	end
end

function VFX.SpecialCharge(tool)
	local windup = Config.Combat.SpecialWindup
	local star = starAttachment(tool)
	if star then
		newEmitter(star, {
			Texture = VFX.Texture("Swirl"),
			LockedToPart = true,
			Lifetime = NumberRange.new(windup + 0.15),
			Size = ns({ { 0, 0.4 }, { 1, 2.4 } }),
			RotSpeed = NumberRange.new(420),
			Transparency = ns({ { 0, 0.3 }, { 0.8, 0 }, { 1, 1 } }),
			LightEmission = 0.35,
			ZOffset = 0.6,
		}):Emit(1)
	end
	boostRates(tool, 3, windup + 0.3)
	pulseLight(tool, 7, windup + 0.4)
	flashTrails(tool, windup + 0.45)
	emit(tool, "StarShimmer", 3)
end

function VFX.SpecialRelease(tool, impact, isLocalAttacker)
	local character = tool.Parent
	local root = character and character:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	impact = impact or VFX.ComputeImpact(character)
	playSound(tool, "SpecialSound")
	local radius = Config.VFX.SpecialSlashRadius
	crescent(character, 90, radius, Config.VFX.SlashWidth * 2, 0.4, 6)
	task.delay(0.06, function()
		crescent(character, 65, radius * 0.8, Config.VFX.SlashWidth * 1.6, 0.35, 4)
	end)
	emit(tool, "SwingSparks", 30)
	-- sheet item 3: the giant streak striking down into the impact
	local rcf = root.CFrame
	local sky = impact + Vector3.new(0, 16, 0) - rcf.LookVector * 9 + rcf.RightVector * 7
	local a0, a1 = worldAttachment(impact), worldAttachment(impact)
	local streak = newBeam(a0, a1, {
		Texture = VFX.Texture("Streak"),
		LightEmission = 0.3,
		Width0 = 3.4,
		Width1 = 3.4,
		ZOffset = 1,
	})
	animate(0.5, function(t)
		a1.WorldPosition = impact:Lerp(sky, math.min(1, t / 0.15))
		streak.Transparency = NumberSequence.new(math.clamp((t - 0.45) / 0.55, 0, 1))
	end)
	for _, inst in ipairs({ a0, a1, streak }) do
		Debris:AddItem(inst, 0.6)
	end
	task.delay(0.1, function()
		burstAt(impact + Vector3.new(0, 0.6, 0), 9, { sparks = 50, embers = 30, light = 9, lightRange = 26, darts = 10 })
		portal(impact + Vector3.new(0, 3, 0) - rcf.LookVector * 1.5, 6, 0.95)
		firePatch(impact, Config.VFX.FirePatchRadius, 0.9)
		local cam = Workspace.CurrentCamera
		if Config.VFX.ScreenFlash and cam and (cam.CFrame.Position - impact).Magnitude < 70 then
			screenFlash()
		end
		if isLocalAttacker and Config.VFX.CameraShake then
			cameraShake(2.4, 0.35)
		end
	end)
end

function VFX.Impact(position, isSpecial)
	burstAt(position, isSpecial and 4.5 or 2.8, {
		sparks = isSpecial and 30 or 16,
		embers = 8,
		light = 4,
		lightRange = 10,
		darts = isSpecial and 6 or 3,
	})
end

-- ---------------------------------------------------------------- idle extras

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
	local shell = tool:FindFirstChild("Shell")
	local star = starAttachment(tool)
	if not (shell and star) then
		return
	end
	local scale = tool:GetAttribute("SwordScale") or 1
	local state = {
		swirls = {},
		flows = {},
		spikes = {},
		body = {},
		nextDart = os.clock() + 1,
		nextPulse = os.clock() + 2,
	}
	local function polyline(raw)
		local path, lengths, total = {}, {}, 0
		for _, p in ipairs(raw) do
			table.insert(path, layoutToLocal(star, p, scale))
		end
		for k = 1, #path - 1 do
			lengths[k] = (path[k + 1] - path[k]).Magnitude
			total += lengths[k]
		end
		return path, lengths, total
	end
	if Config.VFX.Swirls then
		local tex = VFX.Texture("RedSwirl")
		for i, raw in ipairs(Layout.Ribbons) do
			local path, lengths, total = polyline(raw)
			local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
			a0.Name, a1.Name = "Swirl" .. i .. "A", "Swirl" .. i .. "B"
			a0.Parent, a1.Parent = shell, shell
			local trail = Instance.new("Trail")
			trail.Attachment0, trail.Attachment1 = a0, a1
			trail.Texture = tex
			trail.TextureMode = Enum.TextureMode.Stretch
			trail.Lifetime = Config.VFX.SwirlLifetime
			trail.MinLength = 0.02
			trail.FaceCamera = true
			trail.LightEmission = 0.6
			trail.LightInfluence = 0
			trail.WidthScale = ns({ { 0, 1 }, { 1, 0.25 } })
			trail.Transparency = ns({ { 0, 0 }, { 1, 1 } })
			trail.Enabled = false
			trail.Parent = shell
			table.insert(state.swirls, {
				a0 = a0,
				a1 = a1,
				trail = trail,
				path = path,
				lengths = lengths,
				total = total,
				phase = (i - 1) / #Layout.Ribbons,
				last = 0,
			})
		end
	end
	-- One stream of energy round both circles at the star, so they read as one structure.
	-- Its glowing body is the ring of curved "Figure8Body" beams the installer built (a wave
	-- of light runs round it below); here a few bright heads chase each other round the same
	-- closed path, braiding as they go and shedding sparkle dust.
	local figure8 = Layout.Figure8
	if opt("Figure8", true) and figure8 and #figure8 > 2 then
		local path, lengths, total = polyline(figure8)
		local strands = math.max(1, math.floor(opt("FlowStrands", 3)))
		local flowTex, dustTex = VFX.Texture("FlowStroke"), VFX.Texture("Twinkle")
		for i = 1, strands do
			local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
			a0.Name, a1.Name = "Flow" .. i .. "A", "Flow" .. i .. "B"
			a0.Parent, a1.Parent = shell, shell
			local trail = Instance.new("Trail")
			trail.Attachment0, trail.Attachment1 = a0, a1
			trail.Texture = flowTex
			trail.TextureMode = Enum.TextureMode.Stretch
			trail.Lifetime = opt("FlowLifetime", 0.4)
			trail.MinLength = 0.01
			trail.FaceCamera = true
			trail.LightEmission = 1
			trail.LightInfluence = 0
			trail.WidthScale = ns({ { 0, 1 }, { 1, 0.2 } })
			trail.Transparency = ns({ { 0, 0 }, { 1, 1 } })
			trail.Enabled = false
			trail.Parent = shell
			local dust = newEmitter(a1, {
				Texture = dustTex,
				Rate = 16,
				Lifetime = NumberRange.new(0.25, 0.5),
				Speed = NumberRange.new(0.1 * scale, 0.4 * scale),
				SpreadAngle = Vector2.new(180, 180),
				Drag = 3,
				Rotation = NumberRange.new(0, 45),
				Size = ns({ { 0, 0 }, { 0.3, 0.06 * scale }, { 1, 0 } }),
				LightEmission = 1,
				ZOffset = 0.4,
			})
			table.insert(state.flows, {
				a0 = a0,
				a1 = a1,
				trail = trail,
				dust = dust,
				path = path,
				lengths = lengths,
				total = total,
				phase = (i - 1) / strands + 0.1,
			})
		end
	end
	for _, d in ipairs(shell:GetChildren()) do
		if d:IsA("Beam") and d:GetAttribute("Spike") then
			table.insert(state.spikes, d)
		elseif d:IsA("Beam") and d:GetAttribute("Figure8") then
			table.insert(state.body, d)
		end
	end
	table.sort(state.body, function(a, b)
		return a:GetAttribute("Figure8") < b:GetAttribute("Figure8")
	end)
	state.conn = RunService.RenderStepped:Connect(function()
		if not (tool.Parent and shell.Parent) then
			VFX.StopIdle(tool)
			return
		end
		local now = os.clock()
		local cam = Workspace.CurrentCamera
		local near = cam ~= nil and (cam.CFrame.Position - star.WorldPosition).Magnitude < Config.VFX.IdleRange
		local normal = star.CFrame.LookVector -- across the guard plane (the sword's thickness)
		for _, sw in ipairs(state.swirls) do
			-- trace the ribbon from the star outward, pause, repeat
			local s = (now * Config.VFX.SwirlSpeed + sw.phase) % 1.25
			local drawing = near and s <= 1
			if drawing then
				local pos, dir = along(sw.path, sw.lengths, sw.total, s)
				local side = dir.Magnitude > 1e-4 and dir.Unit:Cross(normal) or Vector3.xAxis
				local w = Config.VFX.SwirlWidth * scale * math.sin(math.pi * math.min(1, s * 1.1)) ^ 0.6
				sw.a0.Position = pos - side * w * 0.5
				sw.a1.Position = pos + side * w * 0.5
			end
			-- moving back to the start with the trail on would draw a line across the star
			sw.trail.Enabled = drawing and s >= sw.last
			sw.last = s
		end
		-- the figure-8 path is closed, so the streams never jump and their trails stay on
		local flowSpeed, flowWidth = opt("FlowSpeed", 0.6), opt("FlowWidth", 0.06) * scale
		for _, fl in ipairs(state.flows) do
			if near then
				local s = (now * flowSpeed + fl.phase) % 1
				local pos, dir = along(fl.path, fl.lengths, fl.total, s)
				local side = dir.Magnitude > 1e-4 and dir.Unit:Cross(normal) or Vector3.xAxis
				local braid = side * (0.011 * scale) * math.sin(2 * math.pi * (s * 4 + fl.phase))
				fl.a0.Position = pos + braid - side * flowWidth * 0.5
				fl.a1.Position = pos + braid + side * flowWidth * 0.5
			end
			fl.trail.Enabled = near
			fl.dust.Enabled = near
		end
		if not near then
			return
		end
		-- a wave of light runs round the figure-8's body, moving with the streams
		local count = #state.body
		local function bodyTransparency(k)
			return 0.45 - 0.25 * math.sin(2 * math.pi * (k / count - now * flowSpeed))
		end
		for i, beam in ipairs(state.body) do
			beam.Transparency = NumberSequence.new(bodyTransparency(i - 1), bodyTransparency(i))
		end
		-- the spikes flicker like live energy
		for i, beam in ipairs(state.spikes) do
			local f = 0.5 + 0.5 * math.sin(now * 6 + i * 1.9) * math.sin(now * 2.3 + i)
			beam.Transparency = NumberSequence.new(0.3 * f)
		end
		if Config.VFX.Darts and now >= state.nextDart and #Layout.Spikes > 0 then
			state.nextDart = now + 1.2 + math.random() * 1.4
			local tip = Layout.Spikes[math.random(1, #Layout.Spikes)]
			local tipWorld = shell.CFrame * layoutToLocal(star, tip, scale)
			local dir = tipWorld - star.WorldPosition
			if dir.Magnitude > 1e-3 then
				dart(tipWorld, dir.Unit, 0.45 * scale, 3 * scale, 0.28, 0.16 * scale)
			end
		end
		if now >= state.nextPulse then
			state.nextPulse = now + 2.5 + math.random() * 1.5
			emit(tool, "StarShimmer", 1)
			pulseLight(tool, 3.5, 0.45)
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
	for _, sw in ipairs(state.swirls) do
		sw.trail:Destroy()
		sw.a0:Destroy()
		sw.a1:Destroy()
	end
	for _, fl in ipairs(state.flows) do
		fl.trail:Destroy()
		fl.a0:Destroy()
		fl.a1:Destroy() -- also removes the dust emitter riding on it
	end
	for _, beam in ipairs(state.spikes) do
		if beam.Parent then
			beam.Transparency = NumberSequence.new(0)
		end
	end
end

return VFX
