package tuc.isse.projekt01.view;

import javax.swing.JButton;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.BasicStroke;
import tuc.isse.projekt01.model.Direction;

/**
 * Projekt 04, Task d: DirectionButton - Helper Class for DegreeFrame
 * 
 * Custom JButton for selecting the movement direction (UP, DOWN, LEFT, RIGHT).
 * Each button:
 * - Displays the direction name (UP, DOWN, LEFT, RIGHT)
 * - Stores the Direction enum value as action command for easy retrieval
 * - Shows blue border when selected by the user
 * 
 * This class provides intuitive direction selection in the GUI and visual
 * feedback for the currently selected direction.
 * 
 * @author xiajiong.xu@tu-clausthal.de
 * @version 1.0
 */
public class DirectionButton extends JButton {

    private final Direction direction;
    private boolean selected = false;

    /**
     * Set whether this button is currently selected
     * @param selected True to show selection visual, false otherwise
     */
    public void setSelected(boolean selected) {
        this.selected = selected;
        repaint();
    }

    /**
     * Constructor for DirectionButton
     * @param direction The direction this button represents
     */
    public DirectionButton(Direction direction) {
        super(direction.name()); // Display UP / DOWN / LEFT / RIGHT
        this.direction = direction;

        setFocusPainted(false);
        setFont(new Font("Arial", Font.BOLD, 16));

        // Store direction as action command
        setActionCommand(direction.name());
    }

    /**
     * Get the direction this button represents
     * @return The Direction enum value (UP, DOWN, LEFT, or RIGHT)
     */
    public Direction getDirection() {
        return direction;
    }
    
    /**
     * Custom painting for the direction button
     * @param g Graphics context for drawing
     */
    @Override
    protected void paintComponent(Graphics g) {
        super.paintComponent(g);

        if (selected) {
            Graphics2D g2 = (Graphics2D) g;
            g2.setColor(java.awt.Color.BLUE);
            g2.setStroke(new BasicStroke(3));
            g2.drawRect(2, 2, getWidth() - 4, getHeight() - 4);
        }
    }

}
