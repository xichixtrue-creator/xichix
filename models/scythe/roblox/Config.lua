-- Crimson Reaper settings. Lives in ReplicatedStorage.CrimsonScythe.Config.
-- Safe to edit: re-running the installer keeps an existing Config.

local Config = {}

Config.Colors = {
	Crystal = Color3.fromRGB(205, 16, 34), -- the blade and every crystal (tints their texture)
	Glow = Color3.fromRGB(255, 40, 54), -- the Neon glow: blade edge and the core's heart
	Metal = Color3.fromRGB(58, 42, 44), -- only used if the metal texture didn't come in with the import
	Light = Color3.fromRGB(255, 28, 40), -- the red light the scythe throws around
}

-- How the crystal looks: "Glass" (translucent ruby, the default), "Neon" (solid glow)
-- or "Texture" (opaque, with the painted crystal fractures).
Config.CrystalStyle = "Glass"
Config.CrystalTransparency = 0.2

Config.Combat = {
	SwingCooldown = 0.5,
	ComboReset = 1.1,
	SwingDamage = { 14, 14, 22 },
	HitDelay = 0.15,
	SwingRange = 9,
	SwingWidth = 10,
	SwingHeight = 7,

	-- the special, Crimson Reap: a full spin that hits everything around you
	SpecialCooldown = 7,
	SpecialWindup = 0.4,
	SpecialDamage = 40,
	SpecialRadius = 12,

	DamageHumanoids = true, -- set false if your game handles damage itself (see ScytheHit)
	FriendlyFire = false,
}

-- Keys / buttons for the special (a touch button is added on mobile).
-- Right mouse is left out on purpose: Roblox uses it to turn the camera.
Config.SpecialInputs = { Enum.KeyCode.E, Enum.KeyCode.ButtonY }

-- Optional custom animations ("rbxassetid://123"); empty = Roblox's tool slash / lunge.
Config.Animations = {
	Swing = {},
	Special = "",
}

-- Roll of the crescent slash for each combo step (degrees). 90 = straight down.
Config.SlashAngles = { 75, -70, 100 }

Config.Sounds = {
	Equip = "rbxasset://sounds/unsheath.wav",
	Swing = "rbxasset://sounds/swordslash.wav",
	Special = "rbxasset://sounds/swordlunge.wav",
	Impact = "",
}

-- Paste uploaded image IDs here to override the imported textures, e.g. Shard = "rbxassetid://1".
-- Keys: Ribbon SmokeRibbon Smoke Shard Glow Spark Drip Slash SlashBand Trail GroundGlow
Config.Textures = {}

Config.FallbackTextures = {
	Default = "rbxasset://textures/particles/sparkles_main.dds",
	Smoke = "rbxasset://textures/particles/smoke_main.dds",
	SmokeRibbon = "rbxasset://textures/particles/smoke_main.dds",
}

Config.VFX = {
	IdleRange = 140, -- the moving parts of the aura only run when the camera is this close
	Aura = true, -- the spiralling red / black aura round the shaft and over the blade
	AuraSpeed = 0.7, -- how fast the energy flows along the aura
	SpiralStreams = 3, -- bright streams racing up the spirals
	StreamSpeed = 0.45, -- trips up the spiral per second
	StreamLifetime = 0.35, -- length of each stream's light trail (seconds)
	CorePulse = true, -- the crystal core's light breathes
	ScreenFlash = true,
	CameraShake = true,
	SlashRadius = 6,
	SlashWidth = 1.6,
	ReapRadius = 11, -- size of the Crimson Reap ring
}

return Config
