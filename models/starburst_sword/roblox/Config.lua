-- Starburst Blade settings. Lives in ReplicatedStorage.StarburstSword.Config.
-- Safe to edit: re-running the installer keeps an existing Config.

local Config = {}

-- Colours of the glowing (Neon) parts of the sword.
Config.Colors = {
	Yellow = Color3.fromRGB(255, 232, 140), -- hot core of the blade, ring, spike cores
	Orange = Color3.fromRGB(255, 108, 24), -- blade band, halo, handle band
	Red = Color3.fromRGB(226, 32, 16), -- red band, flame petals
	Ink = Color3.fromRGB(44, 5, 4), -- the dark outlines (blade edge, spikes, eye)
	Handle = Color3.fromRGB(112, 22, 8),
	Sparkle = Color3.fromRGB(255, 255, 255),
	Aura = Color3.fromRGB(255, 118, 40), -- ForceField heat shimmer around the blade
}

Config.Combat = {
	SwingCooldown = 0.38,
	ComboReset = 1.0,
	SwingDamage = { 12, 12, 18 },
	HitDelay = 0.12,
	SwingRange = 7,
	SwingWidth = 7,
	SwingHeight = 6,

	SpecialCooldown = 6,
	SpecialWindup = 0.35,
	SpecialDamage = 35,
	SpecialRange = 14,
	SpecialWidth = 16,

	DamageHumanoids = true, -- set false if your game handles damage itself (see SwordHit)
	FriendlyFire = false,
}

-- Keys / buttons for the special attack (a touch button is added on mobile).
-- Right mouse is left out on purpose: Roblox uses it to turn the camera.
Config.SpecialInputs = { Enum.KeyCode.E, Enum.KeyCode.ButtonY }

-- Optional custom animations ("rbxassetid://123"); empty = Roblox's tool slash / lunge.
Config.Animations = {
	Swing = {},
	Special = "",
}

-- Roll of the slash crescent for each combo step (degrees). 90 = straight down.
Config.SlashAngles = { 70, -65, 95 }

Config.Sounds = {
	Equip = "rbxasset://sounds/unsheath.wav",
	Swing = "rbxasset://sounds/swordslash.wav",
	Special = "rbxasset://sounds/swordlunge.wav",
	Impact = "",
}

-- Paste uploaded image IDs here to override the imported textures, e.g. Starburst = "rbxassetid://1".
-- Keys: BladePaint HandlePaint Streak SlashStrip Trail Starburst Crescent Dart Portal Swirl
-- RedSwirl FireLick Spark Ember Glow Twinkle
Config.Textures = {}

Config.FallbackTextures = {
	Default = "rbxasset://textures/particles/sparkles_main.dds",
	FireLick = "rbxasset://textures/particles/fire_main.dds",
}

Config.VFX = {
	IdleRange = 140, -- idle extras only run when the camera is this close
	Swirls = true, -- red swirl trails tracing the ribbons around the star
	SwirlSpeed = 1.5, -- strokes per second
	SwirlLifetime = 0.45,
	SwirlWidth = 0.07,
	Darts = true, -- fiery darts shooting off the star's spikes now and then
	ScreenFlash = true,
	CameraShake = true,
	SlashRadius = 4.5,
	SlashWidth = 1.1,
	SpecialSlashRadius = 8,
	FirePatchRadius = 6,
}

return Config
